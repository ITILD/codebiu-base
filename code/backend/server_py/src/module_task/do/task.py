"""任务队列模块 task 表模型与请求/响应体定义"""

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column, DateTime, Index, String, Text
from sqlmodel import Field, SQLModel


class QueueTaskStatus(StrEnum):
    """任务队列生命周期状态(与 common.enum.task.TaskStatus 对齐, 便于跨模块复用)"""

    PENDING = "pending"        # 已创建等待调度(排队中)
    RUNNING = "running"        # Celery worker 执行中
    SUCCESS = "success"        # 成功完成
    FAILED = "failed"          # 执行失败(异常/超时)
    CANCELLED = "cancelled"    # 被用户主动取消
    REVOKED = "revoked"        # Celery 侧撤销(与 cancelled 区分来源)


# 非终态集合(轮询/统计时用于判断"活跃任务")
ACTIVE_STATUSES: tuple[str, ...] = (
    QueueTaskStatus.PENDING,
    QueueTaskStatus.RUNNING,
)


class TaskQueueBase(SQLModel):
    """任务队列基础模型(不含表配置)"""

    name: str = Field(max_length=200, description="任务名称")
    task_type: str = Field(
        max_length=50,
        description="任务类型(对应 module_task.tasks.TASK_TYPES 注册表, 如 demo_document)",
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="任务参数 JSON(提交给 worker 的业务数据, 结构由任务类型定义)",
    )
    priority: int = Field(
        default=0,
        description="优先级(0~9, 数值越大越优先, 投递时走 Redis 分级子队列加权消费)",
    )


class TaskQueue(TaskQueueBase, table=True):
    """任务队列表(PostgreSQL 持久化, 状态/进度由 Celery worker 实时回写)"""

    __tablename__ = "task_queue"
    __table_args__ = (
        Index("ix_task_queue_status_created", "status", "created_at"),
    )

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        primary_key=True,
        index=True,
        description="任务唯一标识(同时作为 Celery 的业务追踪键)",
    )
    user_id: str = Field(index=True, description="创建者用户ID")
    status: str = Field(
        default=QueueTaskStatus.PENDING,
        sa_column=Column(String(20), nullable=False, default=QueueTaskStatus.PENDING),
        description="任务状态(pending/running/success/failed/cancelled/revoked)",
    )
    progress: float = Field(
        default=0.0,
        description="完成百分比 0~100(worker 阶段性回写)",
    )
    message: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="当前执行阶段描述(如 '正在解析文档 12/42 页')",
    )
    result: dict | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="执行结果 JSON(worker 完成时写入)",
    )
    error: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="失败原因(status=failed/revoked 时写入)",
    )
    celery_task_id: str | None = Field(
        default=None,
        index=True,
        max_length=64,
        description="Celery AsyncResult ID(用于读取 broker/backend 侧真实状态)",
    )
    invocation_id: str | None = Field(
        default=None,
        index=True,
        max_length=64,
        description="关联的 skill_invocation.invocation_id(REQ-018 三入口双向追溯)",
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="开始执行时间",
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="结束时间(成功/失败/取消)",
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


class TaskQueueCreate(SQLModel):
    """创建任务请求模型"""

    name: str = Field(max_length=200, description="任务名称")
    task_type: str = Field(max_length=50, description="任务类型(需在 TASK_TYPES 注册表中)")
    payload: dict = Field(default_factory=dict, description="任务参数 JSON")
    priority: int | None = Field(
        default=None,
        description="优先级(0~9, 越界自动夹紧; 未传时按类型生效优先级=覆盖值??默认值)",
    )


class TaskQueueResponse(SQLModel):
    """任务详情响应模型(含 Celery 侧状态对照)

    纯任务管理约定: 响应不携带业务信息(payload 参数/result 结果留在库中由业务模块自用),
    仅暴露执行情况(状态/进度/阶段描述/失败原因/时间线)
    """

    id: str
    name: str
    task_type: str
    priority: int
    status: str
    progress: float
    message: str | None = None
    error: str | None = None
    celery_task_id: str | None = None
    # ---- Celery 结果后端侧状态(可能为 None: 未入队/后端不可用) ----
    celery_state: str | None = None       # PENDING/STARTED/PROGRESS/SUCCESS/FAILURE/REVOKED
    celery_progress: float | None = None  # Celery 侧回传的百分比(worker update_state 写入)
    celery_meta: dict | None = None       # PROGRESS 时的完整进度元数据(total/processed/chunks等)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskStatsResponse(SQLModel):
    """任务状态统计(轮询刷新概览卡片)"""

    total: int = 0
    pending: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    cancelled: int = 0


class TaskTypeDef(SQLModel):
    """任务类型定义(注册表条目, 供前端渲染类型下拉与默认模板)"""

    type: str
    name: str
    description: str
    celery_task: str
    default_payload: dict
    default_priority: int = Field(
        default=0,
        description="类型默认优先级(创建未显式指定 priority 时采用; 0~9 越大越优先)",
    )


class TaskTypePriority(SQLModel, table=True):
    """任务类型入队优先级覆盖(运维热调, 不改代码即可调整某类任务的调度优先级)

    同一类型仅一条记录; 删除记录即回落到注册表默认优先级。
    仅影响"之后创建"的任务, 已入队任务不变。
    """

    __tablename__ = "task_type_priority"

    task_type: str = Field(
        primary_key=True,
        max_length=50,
        description="任务类型编码(对应 TASK_TYPES 注册表)",
    )
    priority_override: int = Field(
        description="覆盖后的入队优先级(0~9, 越大越优先)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
        description="最后调整时间",
    )


class TaskTypeView(SQLModel):
    """任务类型视图(注册表条目 + 优先级覆盖状态, 供任务中心优先级热调表)"""

    type: str
    name: str
    description: str
    celery_task: str
    default_payload: dict
    default_priority: int
    priority_override: int | None = Field(
        default=None,
        description="运维覆盖的优先级(None=未覆盖, 用默认值)",
    )
    effective_priority: int = Field(
        description="当前生效的入队优先级(覆盖值 ?? 默认值)",
    )
    queue: str = Field(
        description="按生效优先级路由的消费队列(priority>=7 走交互队列)",
    )


class WorkerInfo(SQLModel):
    """Celery 执行器(worker)运行状态条目"""

    name: str
    queues: list[str] = Field(default_factory=list, description="消费的队列列表")
    concurrency: int = Field(default=0, description="并发槽位数")
    active: int = Field(default=0, description="当前活跃任务数")
    processed: int = Field(default=0, description="累计已处理任务数")
    uptime_seconds: float | None = Field(default=None, description="进程运行时长(秒)")
    active_tasks: list[dict] = Field(
        default_factory=list,
        description="正在执行的任务(name/id/args 摘要)",
    )
    pid: int | None = Field(default=None, description="进程ID")


class WorkerListResponse(SQLModel):
    """执行器状态响应(broker 不可用时 online=0 并带错误提示, 不抛异常)"""

    total: int = 0
    online: int = 0
    workers: list[WorkerInfo] = Field(default_factory=list)
    error: str | None = Field(default=None, description="采集失败原因(可重试)")


class TaskRecoverResponse(SQLModel):
    """手动自愈结果(重派发遗留 PENDING + 清扫僵尸 RUNNING)"""

    recovered: int = Field(default=0, description="重派发的遗留任务数")
    reaped: int = Field(default=0, description="清扫归档的僵尸任务数")


class TaskRegistryResponse(SQLModel):
    """任务类型注册表响应"""

    types: list[TaskTypeDef]
