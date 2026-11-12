"""Agent Tool Adapter(REQ-018 入口②): Skill 契约 → LLM tool schema → SkillRuntime

设计落点(04 设计文档 §4.1/§5.5):
- 只暴露 published 且 agent_callable=True 的 Skill(对话工具清单从注册表生成)
- tool 名 = Manifest.tool_name('.' 映射 '_', W-7), 回查经 tool_name_to_uid 还原
- 失败按 error_class 映射固定文案注入 ToolMessage(W-10: 不向模型裸抛异常栈)
"""

import json
import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, create_model

from module_agent.service.skill_runtime import SkillContext, SkillRuntime
from module_agent.skills.manifest import SkillManifest, tool_name_to_uid
from module_agent.skills.registry import list_manifests

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


def build_tool(manifest: SkillManifest, ctx: SkillContext) -> BaseTool:
    """把 Skill 契约转为 LangChain 工具(闭包捕获调用上下文与 Manifest, 路由 SkillRuntime)

    注: 闭包直接持有 manifest(不经 tool 名反解析 —— 多级命名空间 pack.*/mcp.*
    的 tool 名映射不可逆, W-7 约定仅保证唯一性不保证往返)
    """
    args_model = _args_model_from_schema(manifest)

    async def _run(**kwargs: Any) -> str:
        runtime = SkillRuntime()
        envelope = await runtime.invoke(manifest.uid, dict(kwargs), ctx, mode="inline")
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
    from module_agent.skills.registry import get_skill

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
