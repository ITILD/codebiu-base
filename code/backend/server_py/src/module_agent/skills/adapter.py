"""Agent Tool Adapter(REQ-018 入口②): Skill 契约 → LLM tool schema → SkillRuntime

设计落点(04 设计文档 §4.1/§5.5):
- 只暴露 published 且 agent_callable=True 的 Skill(对话工具清单从注册表生成)
- tool 名 = Manifest.tool_name('.' 映射 '_', W-7), 回查经 tool_name_to_uid 还原
- 失败按 error_class 映射固定文案注入 ToolMessage(W-10: 不向模型裸抛异常栈)

REQ-019 增量(05 设计 §5.1/§5.4):
- **条件注册**: 工具清单按能力/权限/开关门控逐条生成, 门控不通过即不注册
  (模型看不到自己没有的工具, 避免工具幻觉与空烧预算);
- **会话级熔断**: 同一 Skill 连续失败 2 次即从清单摘除并下发 `skill_masked` 事件;
- **版本固定**: 会话开始时快照 Manifest, 会话内不再随后台编辑漂移(CA-09)。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, create_model

from module_agent.service.skill_runtime import SkillContext, SkillRuntime
from module_agent.skills.breaker import SkillCircuitBreaker
from module_agent.skills.manifest import SkillManifest
from module_agent.skills.registry import get_skill, list_manifests

logger = logging.getLogger(__name__)

# error_class → 注入 ToolMessage 的固定文案(W-10; 模型据此决定重试/换路/告知用户)
ERROR_TOOL_MESSAGES: dict[str, str] = {
    "capability_missing": "该能力所需的模型/能力未配置, 请告知用户先在模型管理中配置, 本次无法完成。",
    "invalid_input": "调用参数不合法, 请检查参数名与取值后重试。",
    "transient": "服务暂时不可用(网络/超时), 可稍后重试一次。",
    "resource_exhausted": "系统繁忙, 建议稍后重试。",
    "budget_exceeded": "执行预算耗尽, 已返回部分结果。",
    "invalid_output": "能力输出异常, 已返回原始内容。",
    "permanent": "能力执行失败, 请换一种方式完成或如实告知用户。",
}

# JSON Schema type → pydantic 类型
_TYPE_MAP: dict[str, Any] = {
    "string": (str, ...),
    "integer": (int, ...),
    "number": (float, ...),
    "boolean": (bool, ...),
}


def _args_model_from_schema(manifest: SkillManifest) -> type[BaseModel] | None:
    """input_schema(JSON Schema) → pydantic 参数模型(轻量转换: 基本类型/required/default)"""
    schema = manifest.input_schema or {}
    properties: dict[str, Any] = schema.get("properties") or {}
    if not properties:
        return None
    required = set(schema.get("required") or [])
    fields: dict[str, tuple[type, Any]] = {}
    for name, spec in properties.items():
        json_type = spec.get("type", "string")
        if json_type == "array":
            base_type: type = list[str]
        else:
            base_type = _TYPE_MAP.get(json_type, (str, ...))[0]
        if name in required:
            fields[name] = (base_type, ...)
        else:
            fields[name] = (base_type | None, spec.get("default"))
    return create_model(
        f"{manifest.tool_name}_args",
        __config__=ConfigDict(extra="ignore"),
        **fields,
    )


def build_tool(
    manifest: SkillManifest,
    ctx: SkillContext,
    breaker: SkillCircuitBreaker | None = None,
) -> BaseTool:
    """把 Skill 契约转为 LangChain 工具(闭包捕获调用上下文与 Manifest, 路由 SkillRuntime)

    注: 闭包直接持有 manifest(不经 tool 名反解析 —— 多级命名空间 pack.*/mcp.*
    的 tool 名映射不可逆, W-7 约定仅保证唯一性不保证往返)

    :param breaker: 会话级熔断器(连续失败即熔断并摘除, REQ-019 §5.4)
    """
    args_model = _args_model_from_schema(manifest)

    async def _run(**kwargs: Any) -> str:
        # 版本固定(CA-09): 会话内固定用装配时的 Manifest 快照, 不随后台编辑漂移
        runtime = SkillRuntime()
        envelope = await runtime.invoke(
            manifest.uid, dict(kwargs), ctx, mode="inline", manifest=manifest
        )
        if breaker is not None:
            if envelope.get("status") == "succeeded":
                breaker.record_success(manifest.uid)
            else:
                error = envelope.get("error") or {}
                reason = f"{error.get('class', 'permanent')}: {str(error.get('message'))[:120]}"
                await breaker.record_failure(manifest.uid, reason)
        return _render_tool_result(envelope)

    return StructuredTool.from_function(
        coroutine=_run,
        name=manifest.tool_name,
        description=manifest.description,
        args_schema=args_model,
        metadata={"skill_manifest": manifest},  # runner 展示信息直取(免反解析)
    )


def build_agent_tools(skill_keys: list[str] | None, ctx: SkillContext) -> list[BaseTool]:
    """按 agent 勾选的技能名单构建工具(未注册项跳过告警)

    :param skill_keys: 技能键(支持旧短名自动映射); None=全部 agent_callable 技能;
        空列表=不挂载任何工具(通用助手)
    """
    if skill_keys is None:
        manifests = list_manifests(agent_callable_only=True)
    else:
        manifests = []
        for key in skill_keys:
            manifest = get_skill(key)
            if manifest is None:
                logger.warning("agent 技能未注册, 已跳过: %s", key)
                continue
            if not manifest.agent_callable:
                logger.warning("agent 技能不可对话调用, 已跳过: %s", key)
                continue
            manifests.append(manifest)
    return [build_tool(m, ctx) for m in manifests]


# ── 条件注册(REQ-019 §5.1) ─────────────────────────────────────

#: 运行时特性 → 门控判定函数名(见 ToolGate)
FEATURE_WEB = "web"
FEATURE_SANDBOX = "sandbox"
FEATURE_KNOWLEDGE_BASE = "knowledge_base"


@dataclass
class ToolGate:
    """工具注册门控(能力 / 权限 / 开关 三重)

    - 能力: Skill 声明的 required_capabilities 必须全部可解析(否则不注册);
    - 权限: 仅注册调用上下文授权范围内的 Skill(project_ids 不可扩大, CA-08);
    - 开关: 运行时特性(联网/沙箱/知识库命中)不满足则不注册。
    """

    #: 运行时特性是否具备
    features: set[str] = field(default_factory=set)
    #: 可用能力键集合(已解析)
    available_capabilities: set[str] = field(default_factory=set)
    #: 授权项目范围(空=不限)
    project_ids: list[str] = field(default_factory=list)

    def feature_ok(self, feature: str) -> bool:
        """运行时特性是否满足"""
        return feature in self.features

    def capability_ok(self, manifest: SkillManifest) -> bool:
        """能力是否满足(required 全部可用; 能力组至少一组可用)"""
        for key in manifest.required_capabilities:
            if key not in self.available_capabilities:
                return False
        if manifest.capability_alternatives:
            return any(
                all(key in self.available_capabilities for key in group)
                for group in manifest.capability_alternatives
            )
        return True

    def permission_ok(self, manifest: SkillManifest) -> bool:
        """权限是否满足(需知识库的 Skill 必须命中授权项目范围)"""
        if FEATURE_KNOWLEDGE_BASE in manifest.requires_features:
            return bool(self.project_ids)
        return True


@dataclass
class ToolRegistration:
    """工具注册结果(含未注册原因, 便于观测与前端解释)"""

    tools: list[BaseTool] = field(default_factory=list)
    manifests: list[SkillManifest] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # [{key, reason}]


async def build_gated_tools(
    skill_keys: list[str] | None,
    ctx: SkillContext,
    gate: ToolGate,
    breaker: SkillCircuitBreaker | None = None,
) -> ToolRegistration:
    """按门控条件生成会话级工具清单(REQ-019 §5.1)

    门控顺序: agent_callable → 运行时特性 → 能力 → 权限。
    未通过门控的 Skill **不注册**(模型看不到它没有的工具), 并记录跳过原因。

    :param skill_keys: 技能键名单; None=全部 agent_callable 技能, []=不挂任何工具
    :param ctx: 技能上下文(注入 user_id/project_ids, CA-08)
    :param gate: 门控条件
    :param breaker: 会话级熔断器(已熔断的 Skill 不注册; 熔断事件由 breaker 的 on_mask 下发)
    """
    if skill_keys is None:
        candidates = list_manifests(agent_callable_only=True)
    else:
        candidates = []
        for key in skill_keys:
            manifest = get_skill(key)
            if manifest is None:
                logger.warning("agent 技能未注册, 已跳过: %s", key)
                continue
            if not manifest.agent_callable:
                logger.warning("agent 技能不可对话调用, 已跳过: %s", key)
                continue
            candidates.append(manifest)

    registration = ToolRegistration()
    for manifest in candidates:
        missing = [f for f in manifest.requires_features if not gate.feature_ok(f)]
        if missing:
            registration.skipped.append(
                {"key": manifest.uid, "reason": f"运行特性不满足: {', '.join(missing)}"}
            )
            continue
        if not gate.capability_ok(manifest):
            registration.skipped.append(
                {"key": manifest.uid, "reason": "所需能力不可用"}
            )
            continue
        if not gate.permission_ok(manifest):
            registration.skipped.append(
                {"key": manifest.uid, "reason": "无授权资源范围"}
            )
            continue
        if breaker is not None and breaker.is_masked(manifest.uid):
            registration.skipped.append(
                {"key": manifest.uid, "reason": f"会话内已熔断: {breaker.mask_reason(manifest.uid)}"}
            )
            continue
        registration.manifests.append(manifest)
        registration.tools.append(build_tool(manifest, ctx, breaker=breaker))

    if registration.skipped:
        logger.info(
            "工具条件注册: 命中 %d 项, 跳过 %d 项(%s)",
            len(registration.tools),
            len(registration.skipped),
            "; ".join(f"{s['key']}({s['reason']})" for s in registration.skipped),
        )
    return registration


def _render_tool_result(envelope: dict) -> str:
    """统一信封 → ToolMessage 文本(成功序列化结果; 失败按 error_class 固定文案, W-10)"""
    if envelope.get("status") == "succeeded":
        result = envelope.get("result")
        if isinstance(result, dict):
            # 文本型结果直接透出(text 字段约定), 其余序列化
            if "text" in result and len(result) <= 3:
                suffix = " [降级完成]" if envelope.get("degraded") else ""
                return str(result["text"]) + suffix
            return json.dumps(result, ensure_ascii=False, default=str)
        return json.dumps({"status": "succeeded", "result": result}, ensure_ascii=False, default=str)
    error = envelope.get("error") or {}
    error_class = str(error.get("class") or "permanent")
    template = ERROR_TOOL_MESSAGES.get(error_class, ERROR_TOOL_MESSAGES["permanent"])
    return f"[调用失败:{error_class}] {template} 详情: {str(error.get('message'))[:200]}"
