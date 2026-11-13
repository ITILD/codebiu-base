"""Skill Manifest 契约(REQ-018): Skill 层一等公民的声明模型与校验规则

三层抽象(Model/Skill/Agent)中 Skill 是"单一工作技能"——本文件只定义**契约**,
不定义执行(执行见 service/skill_runtime.py)。内置 Skill 由各领域宿主模块的
代码 Manifest 声明(module_xxx/skills/), 注册表见 skills/registry.py。

契约字段语义(与设计文档 §3.1 一一对应):
- nature: static(零模型可跑) / ai(必需模型) / hybrid(规则主干+局部模型, 可降级)
- execution.modes: inline(进程内硬超时) / queued(落 task_queue 投 Celery)
- capability_alternatives: 能力组(W-6), 如 doc_chunk_index 的
  [[embeddings], [store:bm25]] —— 至少一组全部可满足即可运行, 落到降级组则
  调用结果标记 degraded=true
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# key/namespace 命名约束(全局唯一键 = "{namespace}.{key}", W-7)
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class SkillNature(StrEnum):
    """能力来源: 是否依赖模型及缺失时的行为"""

    STATIC = "static"    # 纯规则/流程/算法, 零模型可运行(CA-06)
    AI = "ai"            # 必须模型参与, 缺失即 capability_missing 快速失败
    HYBRID = "hybrid"    # 规则主干+局部模型, 可选能力缺失降级(degraded=true)


class SkillType(StrEnum):
    """Skill 实现类型(全枚举一步定义, W-15; 交付节奏按批次)"""

    BUILTIN_TOOL = "builtin_tool"      # 内置代码技能(首批交付)
    PROMPT = "prompt"                  # prompt 自定义(批次 2)
    PYTHON_SCRIPT = "python_script"    # python 沙箱脚本(批次 3)
    SCRIPT = "script"                  # 多语言沙箱脚本(bash/node 等, 批次 3)
    MCP_TOOL = "mcp_tool"              # MCP server tool 适配(批次 3)


class SkillCategory(StrEnum):
    """Skill 业务分类(能力中心展示维度)"""

    INGEST = "ingest"          # 文档/数据入库
    RETRIEVAL = "retrieval"    # 检索
    GENERATION = "generation"  # 内容生成
    GOVERNANCE = "governance"  # 治理/管理
    ACTION = "action"          # 通用动作


class ResourceDomain(StrEnum):
    """资源域(队列白名单语义, 批次 1 记录契约, 准入配额批次 2 落地)"""

    PARSE = "parse"
    INDEX = "index"
    LLM = "llm"
    NONE = "none"


class SideEffect(StrEnum):
    """副作用声明(权限/审计/幂等策略依据)"""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"


class ExecutionSpec(BaseModel):
    """执行形态声明: inline/queued 由 SkillRuntime 按此自动选择(§4.2)"""

    modes: list[str] = Field(
        default_factory=lambda: ["inline"],
        description="支持的执行形态: inline / queued",
    )
    inline_timeout_s: int = Field(default=60, ge=1, description="inline 硬超时(秒, CA-05)")
    queued_timeout_s: int = Field(default=1800, ge=1, description="queued 超时(秒)")
    resource_domain: str = Field(default="none", description="资源域(parse/index/llm/none)")
    inline_max_input_bytes: int | None = Field(
        default=None,
        description="输入规模阈值(字节, input.size_hint 超过则转 queued; None 不限)",
    )


class RetrySpec(BaseModel):
    """重试策略(按 error_class 分派见 skill_runtime)"""

    max: int = Field(default=2, ge=0)
    backoff_s: int = Field(default=30, ge=0)


class IdempotencySpec(BaseModel):
    """幂等键声明(CA-03): keys 引用 input 字段名, 拼装指纹去重"""

    keys: list[str] = Field(default_factory=list)


class SkillManifest(BaseModel):
    """Skill 清单(契约核心): 一份声明驱动注册表/运行时/观测/对话工具四个视图"""

    model_config = ConfigDict(frozen=True)

    namespace: str = Field(default="sys", description="命名空间: sys 内置 / usr 自定义")
    key: str = Field(description="技能短名(与 namespace 拼成全局唯一键)")
    name: str = Field(max_length=100, description="展示名称")
    description: str = Field(max_length=2000, description="能力描述(供 LLM 判断何时调用)")
    category: str = Field(default=SkillCategory.ACTION.value, description="业务分类")
    skill_type: str = Field(default=SkillType.BUILTIN_TOOL.value, description="实现类型")
    nature: str = Field(default=SkillNature.STATIC.value, description="能力来源 static/ai/hybrid")
    impl_ref: str = Field(description="实现引用: '模块路径:函数名'(如 module_office.skills.doc_parse.impl:run)")
    version: str = Field(default="1", description="内置代码版本(随 git 演进)")

    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="输入 JSON Schema(必含 required, CA-03); 允许附加约定字段 size_hint 供模式决策",
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="输出 JSON Schema(必含 properties, CA-03)",
    )

    required_capabilities: list[str] = Field(
        default_factory=list, description="必需能力键, 任一缺失即 capability_missing"
    )
    optional_capabilities: list[str] = Field(
        default_factory=list, description="可选能力键, 缺失时降级(degraded=true)"
    )
    capability_alternatives: list[list[str]] = Field(
        default_factory=list,
        description="能力组(W-6): 组间任一可满足即可运行, 落降级组则 degraded",
    )
    model_bindings: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="能力 → 绑定声明({model|func, policy}); 批次 1 以运行时解析链为准",
    )

    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    idempotency: IdempotencySpec = Field(default_factory=IdempotencySpec)
    retry: RetrySpec = Field(default_factory=RetrySpec)
    progress: bool = Field(default=True, description="是否上报进度(queued 前提)")
    cancel: bool = Field(default=False, description="是否支持取消")
    side_effects: str = Field(default=SideEffect.READ.value, description="副作用声明")
    agent_callable: bool = Field(default=True, description="是否暴露给 ai_agent tool-calling")
    prompt: dict[str, Any] | None = Field(
        default=None,
        description="prompt 类型专用(批次 2): {template: '含{{字段}}占位', output_format: 'text'|'json'};"
        " 执行器为运行时内建(模板渲染 + chat 模型调用), 不需要 impl_ref 指向业务代码",
    )
    script: dict[str, Any] | None = Field(
        default=None,
        description="script/python_script 类型专用(批次 3): {language: 'python'|'bash'|'node', "
        "code: '入口脚本内容', files: {相对路径: 伴随文件内容}(协作模块/模板/Schema, "
        "社区包多文件脚本树), env_allowed: [显式放行的环境变量名]}; "
        "沙箱执行器内建: 子进程 + 空环境 + 临时工作目录 + 硬超时 + 输出截断, "
        "stdin=JSON(input), stdout 末行 JSON 解析为结果(否则整体作为 text)",
    )

    @property
    def uid(self) -> str:
        """全局唯一键 {namespace}.{key}(W-7)"""
        return f"{self.namespace}.{self.key}"

    @property
    def tool_name(self) -> str:
        """LLM tool-calling 名称: '.' 映射为 '_'(W-7, 主流协议字符集限制), 回查还原"""
        return self.uid.replace(".", "_")

    def check_invariants(self) -> None:
        """发布/注册期校验(§3.1 校验规则); 违反即抛 ValueError 阻止注册(启动失败)"""
        errors: list[str] = []
        # namespace 允许点分段多级(pack.{包名} / mcp.{server}, W-14/W-15), 每段须合法
        namespace_segments = self.namespace.split(".") if self.namespace else []
        if not namespace_segments or not all(_NAME_PATTERN.match(seg) for seg in namespace_segments):
            errors.append(f"namespace 非法: {self.namespace!r}")
        if not _NAME_PATTERN.match(self.key):
            errors.append(f"key 非法: {self.key!r}")
        if self.nature not in tuple(v.value for v in SkillNature):
            errors.append(f"nature 非法: {self.nature!r}")
        if self.skill_type not in tuple(v.value for v in SkillType):
            errors.append(f"skill_type 非法: {self.skill_type!r}")
        if not self.input_schema.get("required"):
            errors.append("input_schema.required 不得为空(CA-03)")
        if not self.output_schema.get("properties"):
            errors.append("output_schema.properties 不得为空(CA-03)")
        if self.nature == SkillNature.STATIC.value and (
            self.required_capabilities or self.optional_capabilities or self.model_bindings
        ):
            errors.append("nature=static 时 required/optional capabilities 与 model_bindings 必须为空")
        if self.nature == SkillNature.AI.value and not self.required_capabilities:
            errors.append("nature=ai 时 required_capabilities 不得为空")
        if self.nature == SkillNature.HYBRID.value and not (
            self.optional_capabilities or self.capability_alternatives
        ):
            errors.append("nature=hybrid 必须声明可选能力或能力组(降级依据)")
        if self.skill_type in (SkillType.PROMPT.value, SkillType.PYTHON_SCRIPT.value, SkillType.SCRIPT.value):
            template = (self.prompt or {}).get("template")
            code = (self.script or {}).get("code")
            if self.skill_type == SkillType.PROMPT.value and (
                not isinstance(template, str) or not template.strip()
            ):
                errors.append("skill_type=prompt 必须提供非空 prompt.template")
            if self.skill_type in (SkillType.PYTHON_SCRIPT.value, SkillType.SCRIPT.value) and (
                not isinstance(code, str) or not code.strip()
            ):
                errors.append(f"skill_type={self.skill_type} 必须提供非空 script.code")
            if self.skill_type == SkillType.PROMPT.value and self.script is not None:
                errors.append("script 字段仅 script/python_script 类型允许声明")
            if self.skill_type in (SkillType.PYTHON_SCRIPT.value, SkillType.SCRIPT.value) and self.prompt is not None:
                errors.append("prompt 字段仅 skill_type=prompt 允许声明")
        elif self.prompt is not None or self.script is not None:
            errors.append("prompt/script 字段仅 prompt/script 类型 Skill 允许声明")
        if "queued" in self.execution.modes and not self.progress:
            errors.append("无进度上报的 Skill 不得声明 queued(CA-05)")
        if errors:
            raise ValueError(f"Skill Manifest 校验失败 [{self.uid}]: " + "; ".join(errors))

    @model_validator(mode="after")
    def _validate(self) -> "SkillManifest":
        self.check_invariants()
        return self


def tool_name_to_uid(tool_name: str) -> str:
    """LLM 工具名还原为注册表键(与 SkillManifest.tool_name 互逆)"""
    return tool_name.replace("_", ".", 1)
