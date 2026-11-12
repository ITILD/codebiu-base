"""job Agent Manifest: static_agent 步骤声明模型与注册表"""

from pydantic import BaseModel, Field


class AgentStepDef(BaseModel):
    """job 步骤声明(一次调用一个 Skill; fan_out 时按展开项并发调用)"""

    id: str = Field(description="步骤ID(depends_on/条件表达式引用名)")
    skill: str = Field(description="Skill 全局键(sys.doc_parse)")
    fan_out: str | None = Field(
        default=None,
        description="展开字段名: job input[fan_out] 为列表时逐项并发调用; None 单项调用",
    )
    item_key: str = Field(
        default="document_id",
        description="展开项业务键(幂等与步骤间结果关联: 同键项传递产物)",
    )
    depends_on: list[str] = Field(default_factory=list, description="前置步骤ID(批次 1 为线性序)")
    when: str | None = Field(
        default=None, description="步骤级准入表达式(引用前序步骤聚合摘要; False 整步跳过)"
    )
    skip_if: str | None = Field(
        default=None,
        description="展开项级过滤表达式(引用 item 与依赖步骤同键项结果; True 该项跳过)",
    )
    consume: dict[str, str] = Field(
        default_factory=dict,
        description="产物传递: 本步输入字段 -> '依赖步骤ID.输出字段'(按 item_key 关联同键项)",
    )
    input_resolver: str | None = Field(
        default=None,
        description="展开项输入准备器 '模块:函数': async fn(item, ctx) -> dict; "
        "在执行侧(inline/worker 同进程)物化展开项补充字段(如文档落盘 file_path), "
        "返回值可携带 __cleanup_paths 列表交 job 统一清理",
    )
    input: dict = Field(default_factory=dict, description="固定入参(展开项字段并入后传给 Skill)")
    on_error: str = Field(
        default="collect", description="单项失败策略: collect 收集继续 / fail_fast 整步中止"
    )


class AgentJobManifest(BaseModel):
    """内置 job Agent 声明(代码 Manifest; ai_agent(chat)形态不在此, 沿用既有问答图)"""

    namespace: str = Field(default="sys")
    key: str
    name: str
    description: str
    agent_kind: str = Field(default="job", description="形态: job(static_agent 批处理)")
    decision_mode: str = Field(default="rule", description="决策方式: rule 固定步骤")
    version: str = Field(default="1")
    steps: list[AgentStepDef]
    runtime_policy: dict = Field(
        default_factory=dict,
        description="运行策略(priority_class/max_parallel/budget; 队列准入配额批次 2 落地)",
    )

    @property
    def agent_key(self) -> str:
        return f"{self.namespace}.{self.key}"

    def check_invariants(self) -> None:
        """编排声明校验: 步骤引用的 Skill 须已注册; depends_on/consume 来源须在先前步骤"""
        from module_agent.skills.registry import get_skill

        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"[{self.agent_key}] 步骤 ID 重复: {step.id}")
            if get_skill(step.skill) is None:
                raise ValueError(f"[{self.agent_key}] 步骤 {step.id} 引用未注册 Skill: {step.skill}")
            for dep in step.depends_on:
                if dep not in seen:
                    raise ValueError(f"[{self.agent_key}] 步骤 {step.id} 依赖未声明的先行步骤: {dep}")
            for source in step.consume.values():
                dep_id = source.split(".", 1)[0]
                if dep_id not in seen:
                    raise ValueError(f"[{self.agent_key}] 步骤 {step.id} consume 来源未声明: {source}")
            if step.on_error not in ("collect", "fail_fast"):
                raise ValueError(f"[{self.agent_key}] 步骤 {step.id} on_error 非法: {step.on_error}")
            seen.add(step.id)


# 内置 job Agent 注册表(agent_key -> AgentJobManifest)
AGENT_JOBS: dict[str, AgentJobManifest] = {}


def register_agent_job(manifest: AgentJobManifest) -> AgentJobManifest:
    manifest.check_invariants()
    existed = AGENT_JOBS.get(manifest.agent_key)
    if existed is not None:
        if existed == manifest:
            return existed
        raise ValueError(f"job Agent 注册冲突: {manifest.agent_key}")
    AGENT_JOBS[manifest.agent_key] = manifest
    return manifest


def get_agent_job(agent_key: str) -> AgentJobManifest | None:
    return AGENT_JOBS.get(agent_key)


def list_agent_jobs() -> list[AgentJobManifest]:
    return list(AGENT_JOBS.values())
