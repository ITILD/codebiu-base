"""智能体模块 agent_agent 表模型与请求/响应体定义(REQ-013)"""

from sqlmodel import Column, DateTime, Field, SQLModel, JSON
from uuid import uuid4
from datetime import datetime, timezone


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
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
