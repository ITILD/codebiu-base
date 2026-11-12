"""智能体模块 Skill 资产与调用观测表(REQ-018)

三张表:
- ai_skill / ai_skill_version: Skill 资产登记(内置只读同步, 双生命周期 W-8;
  自定义 DB 状态机属后续批次, 表结构一步到位)
- skill_invocation: 统一调用观测(CA-11)——无论哪条入口/哪种执行形态, 每次调用一行;
  与 task_queue 经 task_id 双向关联
"""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class InvocationStatus(StrEnum):
    """Skill 调用生命周期"""

    PENDING = "pending"      # queued 已入队未执行
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SkillPublishStatus(StrEnum):
    """Skill 资产状态(内置=同步即 published, 删除即下线; 自定义走 DB 状态机)"""

    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    DRAFT = "draft"          # 仅自定义 Skill 使用


class AiSkillBase(SQLModel):
    """Skill 资产登记基础模型"""

    key: str = Field(max_length=120, index=True, description="全局唯一键 {namespace}.{key}")
    namespace: str = Field(max_length=60, description="命名空间(sys/usr/pack.*/mcp.*)")
    name: str = Field(max_length=100, description="展示名称")
    description: str = Field(default="", description="能力描述")
    category: str = Field(default="action", max_length=30, description="业务分类")
    skill_type: str = Field(default="builtin_tool", max_length=30, description="实现类型")
    nature: str = Field(default="static", max_length=10, description="能力来源 static/ai/hybrid")
    origin: str = Field(default="builtin", max_length=30, description="来源: builtin/external(包名或 MCP server)")
    origin_version: str = Field(default="", max_length=60, description="外部来源版本(内置为空)")
    owner_user_id: str | None = Field(
        default=None, max_length=50,
        description="自定义 Skill 创建者(REQ-018 批次 2 prompt Skill 归属; 内置为空)",
    )
    current_version: str = Field(default="1", max_length=30, description="当前生效版本")
    status: str = Field(
        default=SkillPublishStatus.PUBLISHED,
        sa_column=Column(String(20), nullable=False, default=SkillPublishStatus.PUBLISHED),
        description="发布状态(内置同步即 published, W-8 双生命周期)",
    )
    deprecated: bool = Field(default=False, description="废弃提示(仍可调用, 前端置灰)")


class AiSkill(AiSkillBase, table=True):
    """Skill 资产表(只读同步内置 Manifest; 自定义 Skill 后续批次)"""

    __tablename__ = "ai_skill"
    __table_args__ = (Index("ix_ai_skill_key_unique", "key", unique=True),)

    id: str = Field(
        default_factory=lambda: uuid4().hex, primary_key=True, index=True,
        description="唯一标识符",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
    )


class AiSkillVersion(SQLModel, table=True):
    """Skill 版本表: 承载 schema/绑定/执行声明快照与 config_hash(CA-09 版本快照依据)"""

    __tablename__ = "ai_skill_version"
    __table_args__ = (Index("ix_ai_skill_version_skill", "skill_id", "version"),)

    id: str = Field(
        default_factory=lambda: uuid4().hex, primary_key=True, index=True,
    )
    skill_id: str = Field(index=True, description="所属 ai_skill.id")
    version: str = Field(max_length=30, description="版本号(内置随代码声明)")
    config_hash: str = Field(max_length=64, index=True, description="Manifest 内容哈希(声明漂移检测)")
    manifest_snapshot: dict = Field(
        sa_column=Column(JSONB, nullable=False),
        description="Manifest 完整快照(运行期固定版本依据, CA-09)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )


class SkillInvocation(SQLModel, table=True):
    """Skill 调用观测表(CA-11): 三条入口/两种形态的所有调用都落此表"""

    __tablename__ = "skill_invocation"
    __table_args__ = (
        Index("ix_skill_invocation_skill_created", "skill_key", "created_at"),
        Index("ix_skill_invocation_user", "user_id"),
        Index("ix_skill_invocation_task", "task_id"),
    )

    invocation_id: str = Field(
        default_factory=lambda: uuid4().hex, primary_key=True, index=True,
        description="调用唯一标识(对外句柄, 对话轮询/调试台共用)",
    )
    skill_key: str = Field(max_length=120, description="Skill 全局键(sys.doc_parse)")
    skill_version: str = Field(default="1", max_length=30, description="调用时生效版本(CA-09)")
    mode: str = Field(max_length=10, description="实际执行形态: inline/queued")
    status: str = Field(
        default=InvocationStatus.PENDING,
        sa_column=Column(String(20), nullable=False, default=InvocationStatus.PENDING),
    )
    priority_class: str = Field(default="standard", max_length=20, description="优先级类 interactive/standard/batch")
    # 幂等指纹(idempotency.keys 引用字段拼装哈希; 同指纹的进行中/成功调用直接复用, §4.5)
    idempotency_key: str | None = Field(
        default=None, max_length=128, index=True,
        description="幂等指纹(skill+声明的键字段); 声明 keys 为空则为 None(不去重)",
    )
    input_summary: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False),
        description="输入摘要(幂等键字段原文+规模提示, 不存大产物)",
    )
    output: dict | None = Field(
        default=None, sa_column=Column(JSONB),
        description="输出结果(大产物仅存摘要/引用, 完整产物由编排层内存传递)",
    )
    degraded: bool = Field(default=False, description="是否降级完成(可选能力缺失/降级能力组)")
    error_class: str | None = Field(
        default=None, max_length=30,
        description="失败分类(§3.4: invalid_input/capability_missing/transient/permanent/...)",
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text), description="失败原因")
    duration_ms: int | None = Field(default=None, description="执行耗时(毫秒)")
    tokens: int = Field(default=0, description="token 成本(static 路线恒 0)")
    task_id: str | None = Field(
        default=None, index=True, max_length=64,
        description="queued 形态关联的 task_queue.id(双向关联)",
    )
    entry: str | None = Field(default=None, max_length=30, description="触发入口: web/agent/task/debug")
    user_id: str = Field(index=True, description="调用者用户ID(资源授权范围载体, CA-08)")
    trace_id: str | None = Field(default=None, max_length=64, description="链路追踪ID")
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
    )
