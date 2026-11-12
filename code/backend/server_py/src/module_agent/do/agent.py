"""智能体模块 agent_agent 表模型与请求/响应体定义(REQ-013/REQ-018)"""

from enum import StrEnum
from sqlmodel import Column, DateTime, Field, SQLModel, String, JSON
from uuid import uuid4
from datetime import datetime, timezone


class AgentKind(StrEnum):
    """Agent 形态(REQ-018 两形态): chat 会话流式 / job 批处理编排"""

    CHAT = "chat"
    JOB = "job"


class DecisionMode(StrEnum):
    """决策方式: rule 固定工作流(static_agent) / model 模型决策(ai_agent) / hybrid"""

    RULE = "rule"
    MODEL = "model"
    HYBRID = "hybrid"


class AgentBase(SQLModel):
    """智能体基础模型"""

    name: str = Field(..., max_length=100, description="名称")
    description: str = Field(default="", max_length=500, description="描述")
    # 系统提示词(空串走内置默认提示词)
    default_prompt: str = Field(default="", description="默认系统提示词")
    # 默认关联知识库(项目)ID列表, 供 rag_qa 技能回退
    default_project_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="默认关联知识库ID列表",
    )
    # 技能名单(必须全部在 Skill 注册表中)
    skills: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="技能列表(注册表内的技能名)",
    )
    owner_user_id: str = Field(..., max_length=50, index=True, description="创建者用户ID")
    is_public: bool = Field(default=False, description="是否公开(公开对所有用户可见)")
    is_builtin: bool = Field(default=False, description="是否内置(内置不可删除)")
    # ---- REQ-018 三层抽象扩展: Agent 两形态(既有行默认 chat/model 保持兼容) ----
    agent_kind: str = Field(
        default=AgentKind.CHAT,
        sa_column=Column(String(10), nullable=False, server_default="chat"),
        description="形态: chat 会话流式 / job 批处理编排",
    )
    decision_mode: str = Field(
        default=DecisionMode.MODEL,
        sa_column=Column(String(10), nullable=False, server_default="model"),
        description="决策方式: rule 固定步骤(static_agent) / model 模型决策(ai_agent) / hybrid",
    )
    steps: list[dict] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="job 形态步骤声明(线性+fan_out+depends_on+when/skip_if; 内置 Agent 只读同步)",
    )
    execution_strategy: str | None = Field(
        default=None, max_length=20,
        description="ai_agent 执行策略 direct/react/plan_execute(仅 decision_mode=model 生效)",
    )



class Agent(AgentBase, table=True):
    """智能体数据库模型"""

    __tablename__ = "agent_agent"

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        primary_key=True,
        index=True,
        description="唯一标识符",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="创建时间",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
        description="最后更新时间",
    )


class AgentCreate(SQLModel):
    """创建智能体的请求模型"""

    name: str = Field(..., min_length=1, max_length=100, description="名称")
    description: str = Field(default="", max_length=500, description="描述")
    default_prompt: str = Field(default="", description="默认系统提示词")
    default_project_ids: list[str] = Field(default_factory=list, description="默认知识库ID列表")
    skills: list[str] = Field(default_factory=list, description="技能列表")
    is_public: bool = Field(default=False, description="是否公开")


class AgentUpdate(SQLModel):
    """更新智能体的请求模型"""

    name: str | None = Field(default=None, min_length=1, max_length=100, description="名称")
    description: str | None = Field(default=None, max_length=500, description="描述")
    default_prompt: str | None = Field(default=None, description="默认系统提示词")
    default_project_ids: list[str] | None = Field(default=None, description="默认知识库ID列表")
    skills: list[str] | None = Field(default=None, description="技能列表")
    is_public: bool | None = Field(default=None, description="是否公开")


class AgentResponse(SQLModel):
    """智能体响应模型"""

    id: str = Field(..., description="唯一标识符")
    name: str = Field(..., description="名称")
    description: str = Field(default="", description="描述")
    default_prompt: str = Field(default="", description="默认系统提示词")
    default_project_ids: list[str] = Field(default_factory=list, description="默认知识库ID列表")
    skills: list[str] = Field(default_factory=list, description="技能列表")
    owner_user_id: str = Field(..., description="创建者用户ID")
    is_public: bool = Field(default=False, description="是否公开")
    is_builtin: bool = Field(default=False, description="是否内置")
    agent_kind: str = Field(default="chat", description="形态: chat/job")
    decision_mode: str = Field(default="model", description="决策方式: rule/model/hybrid")
    steps: list[dict] | None = Field(default=None, description="job 步骤声明")
    execution_strategy: str | None = Field(default=None, description="ai_agent 执行策略")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
