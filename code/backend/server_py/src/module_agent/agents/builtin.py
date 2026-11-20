"""内置对话 Agent Manifest(模式即 Agent, REQ-019 设计 §2.1)

背景(05 设计 §2.1):
- 问答的 `fast` / `thinking` 不再是散落在函数签名里的布尔开关, 而是两个**代码内建**
  的对话 Agent(`builtin_fast` / `builtin_thinking`); 模式配置 `chat_modes` 挂在 Agent 上。
- `deep` 是 thinking Agent 内部的**升级执行模式**, 不是第三个 Agent。
- 代码 Manifest 是唯一事实源, 只读同步进 `agent_agent` 表(同 Skill 的双生命周期原则,
  04 设计 W-8); 管理员的调整落在 `config_override`, 不改代码。

规则(设计 §2.1):
- 内置 Agent 不可删除(删除即下线该模式入口); 模式解析只认内置两者的 `chat_modes`,
  保证策略有唯一来源。
- 模式配置优先级: 内置 Agent `chat_modes` > 平台配置节 > 硬编码默认值(三级回退,
  配置缺失不崩)。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

ThinkLevel = Literal["off", "low", "high"]


class ChatModeConfig(BaseModel):
    """单个执行模式的运行参数(设计 §2.1 chat_modes 各项)"""

    think_level: ThinkLevel = Field(default="off", description="思考档位")
    search_rounds: int = Field(default=1, description="检索轮次")
    max_loops: int = Field(default=2, description="ReAct 轮次上限")
    max_model_calls: int = Field(default=3, description="模型调用上限")
    max_tool_calls: int = Field(default=4, description="工具调用上限")
    wall_clock_s: int = Field(default=30, description="墙钟预算(秒)")


class BuiltinChatAgent(BaseModel):
    """内置对话 Agent 的代码 Manifest"""

    key: str = Field(description="Agent 唯一键(同步进 agent_agent.id)")
    name: str = Field(description="展示名")
    agent_kind: Literal["chat"] = Field(default="chat")
    decision_mode: Literal["model"] = Field(default="model")
    execution_strategy: Literal["direct", "react", "plan_execute"] = Field(
        default="direct", description="执行策略: direct=单轮/react=有界 ReAct/plan_execute=五拍协议"
    )
    description: str = Field(default="", description="Agent 说明")
    skills: list[str] = Field(default_factory=list, description="静态技能名单(空=走条件注册)")
    chat_modes: dict[str, ChatModeConfig] = Field(
        default_factory=dict, description="模式名 → 运行参数"
    )
    system_prompt: str = Field(default="", description="系统提示词(空=由执行器默认生成)")


# ── 内置对话 Agent ──────────────────────────────────────────────

BUILTIN_FAST = BuiltinChatAgent(
    key="builtin_fast",
    name="快速",
    description="固定 RAG 流程: 按固定次数检索重检 + 直答, 模型不开启思考",
    execution_strategy="direct",
    chat_modes={
        "fast": ChatModeConfig(
            think_level="off",
            search_rounds=1,
            max_loops=2,
            max_model_calls=3,
            max_tool_calls=4,
            wall_clock_s=30,
        ),
        "deep": ChatModeConfig(
            think_level="high",
            search_rounds=3,
            max_loops=6,
            max_model_calls=8,
            max_tool_calls=12,
            wall_clock_s=90,
        ),
    },
    system_prompt=(
        "你是企业内部知识库问答助手。直接依据检索到的资料回答, "
        "资料不足时如实说明, 不要编造。"
    ),
)

BUILTIN_THINKING = BuiltinChatAgent(
    key="builtin_thinking",
    name="思考",
    description="ReAct 智能体: 有界多轮取证 + 精排融合, 模型默认开启思考",
    execution_strategy="react",
    chat_modes={
        "thinking": ChatModeConfig(
            think_level="low",
            search_rounds=2,
            max_loops=4,
            max_model_calls=6,
            max_tool_calls=8,
            wall_clock_s=60,
        ),
        "deep": ChatModeConfig(
            think_level="high",
            search_rounds=3,
            max_loops=6,
            max_model_calls=8,
            max_tool_calls=12,
            wall_clock_s=90,
        ),
    },
    system_prompt=(
        "你是企业内部知识库深度问答助手。先规划取证路径(需要哪些资料/是否需要多源交叉), "
        "再调用工具取证, 最后基于证据作答并标注来源。"
    ),
)

#: 全部内置对话 Agent(模式解析的唯一来源)
BUILTIN_CHAT_AGENTS: dict[str, BuiltinChatAgent] = {
    BUILTIN_FAST.key: BUILTIN_FAST,
    BUILTIN_THINKING.key: BUILTIN_THINKING,
}


def get_builtin_chat_agent(key: str) -> BuiltinChatAgent | None:
    """取内置对话 Agent Manifest"""
    return BUILTIN_CHAT_AGENTS.get(key)


def builtin_chat_agents() -> list[BuiltinChatAgent]:
    """全部内置对话 Agent(顺序稳定)"""
    return list(BUILTIN_CHAT_AGENTS.values())


def resolve_mode_config(agent_key: str, mode: str) -> ChatModeConfig | None:
    """内置 Agent 的某档模式配置; 不存在返回 None(由调用方回退)"""
    agent = BUILTIN_CHAT_AGENTS.get(agent_key)
    if agent is None:
        return None
    return agent.chat_modes.get(mode)


def mode_defaults() -> dict[str, dict[str, Any]]:
    """硬编码默认档位(平台配置与内置 Manifest 都缺失时的最后回退, 设计 §2.1)"""
    return {
        "fast": ChatModeConfig(
            think_level="off", search_rounds=1,
            max_loops=2, max_model_calls=3, max_tool_calls=4, wall_clock_s=30,
        ).model_dump(),
        "thinking": ChatModeConfig(
            think_level="low", search_rounds=2,
            max_loops=4, max_model_calls=6, max_tool_calls=8, wall_clock_s=60,
        ).model_dump(),
        "deep": ChatModeConfig(
            think_level="high", search_rounds=3,
            max_loops=6, max_model_calls=8, max_tool_calls=12, wall_clock_s=90,
        ).model_dump(),
    }
