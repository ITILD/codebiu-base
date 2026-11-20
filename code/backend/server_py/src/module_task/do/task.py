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
    """Celery 执行器(worker)运行状态条目(inspect 实时数据 + 心跳注册合并)"""

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
    # ---- 心跳注册合并字段(带默认, 向后兼容无心跳场景) ----
    ip: str | None = Field(default=None, description="实例出口 IP(心跳注册)")
    hostname: str | None = Field(default=None, description="实例主机名/容器 hostname")
    pool: str | None = Field(default=None, description="执行池类型(solo/prefork/threads)")
    status: str = Field(default="online", description="在线状态(online/offline)")
    started_at: str | None = Field(default=None, description="启动时间(ISO, 心跳注册)")
    last_seen: str | None = Field(
        default=None, description="最近心跳时间(ISO, offline 时展示)"
    )


class WorkerListResponse(SQLModel):
    """执行器状态响应(broker 不可用时 online=0 并带错误提示, 不抛异常)"""

    total: int = 0
    online: int = 0
    workers: list[WorkerInfo] = Field(default_factory=list)
    error: str | None = Field(default=None, description="采集失败原因(可重试)")


# ################ 队列注册表(逻辑队列动态增减) ################

class QueueRegistryStatus(StrEnum):
    """队列注册表状态"""

    ENABLED = "enabled"    # 启用: worker 动态订阅 + 派发路由准入
    DISABLED = "disabled"  # 停用: worker 退订 + 派发回落默认队列


class TaskQueueRegistry(SQLModel, table=True):
    """
    队列注册表(逻辑队列的事实来源): 加/撤队列落库即生效(秒级动态订阅), 不动容器

    队列数弹性 ≠ 进程数弹性: 本表只管"谁消费哪些队列"(celery 动态订阅),
    worker 副本伸缩(容器数)由 sys_worker_host + agent(P3)负责。
    """

    __tablename__ = "sys_task_queue_registry"

    queue_name: str = Field(
        primary_key=True, max_length=100, description="队列名(broker 物理队列名)"
    )
    name: str = Field(default="", max_length=200, description="显示名")
    description: str | None = Field(
        default=None, sa_column=Column(Text), description="用途说明"
    )
    tenant: str | None = Field(
        default=None, max_length=100, index=True,
        description="租户隔离预留(None=公共队列)",
    )
    resource_class: str = Field(
        default="default", max_length=50, index=True,
        description="资源池分组预留(default=通用池, 未来按 CPU/GPU/IO 画像分组)",
    )
    min_replicas: int = Field(
        default=0, description="最小副本数预留(未来自动伸缩下限)"
    )
    max_replicas: int = Field(
        default=0, description="最大副本数预留(0=不限)"
    )
    status: str = Field(
        default=QueueRegistryStatus.ENABLED,
        sa_column=Column(String(20), nullable=False, default=QueueRegistryStatus.ENABLED),
        description="状态(enabled=启用/disabled=停用)",
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


class TaskQueueRegistryCreate(SQLModel):
    """创建队列请求体"""

    queue_name: str = Field(max_length=100, description="队列名(字母/数字/下划线)")
    name: str = Field(default="", max_length=200, description="显示名")
    description: str | None = None
    tenant: str | None = Field(default=None, max_length=100, description="租户预留")
    resource_class: str = Field(default="default", max_length=50, description="资源池预留")


class TaskQueueRegistryUpdate(SQLModel):
    """更新队列请求体(全可选, 仅传变更字段)"""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    tenant: str | None = Field(default=None, max_length=100)
    resource_class: str | None = Field(default=None, max_length=50)
    min_replicas: int | None = Field(default=None, ge=0)
    max_replicas: int | None = Field(default=None, ge=0)
    status: QueueRegistryStatus | None = None


class TaskQueueRegistryView(SQLModel):
    """队列注册表视图(含实时订阅 worker 数与积压深度)"""

    queue_name: str
    name: str
    description: str | None = None
    tenant: str | None = None
    resource_class: str
    min_replicas: int
    max_replicas: int
    status: str
    created_at: datetime
    updated_at: datetime
    subscribers: int = Field(default=0, description="当前订阅该队列的 worker 数(inspect)")
    backlog: int = Field(default=0, ge=0, description="队列积压消息数(broker LLEN, 不可用时为 0)")


# ################ worker 宿主机注册表(P3: agent 动态启停) ################

class WorkerHost(SQLModel, table=True):
    """
    worker 宿主机注册表: 每台部署了 task_worker 的宿主机登记 agent 地址,
    主服务经 agent(挂 docker.sock 的轻量 HTTP 服务)查看容器/伸缩副本。
    """

    __tablename__ = "sys_worker_host"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True, index=True)
    host_name: str = Field(
        max_length=100, unique=True, index=True, description="主机名(唯一)"
    )
    agent_url: str = Field(
        max_length=300, description="agent 地址(http://host:8700)"
    )
    agent_token: str | None = Field(
        default=None, sa_column=Column(Text), description="agent Bearer token(密文存储语义, 响应打码)"
    )
    description: str | None = Field(default=None, sa_column=Column(Text))
    enabled: bool = Field(default=True, description="是否启用(停用后不再聚合/运维)")
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


class WorkerHostCreate(SQLModel):
    """登记 worker 宿主机请求体"""

    host_name: str = Field(max_length=100)
    agent_url: str = Field(max_length=300)
    agent_token: str | None = None
    description: str | None = None
    enabled: bool = True


class WorkerHostUpdate(SQLModel):
    """更新 worker 宿主机请求体(全可选)"""

    agent_url: str | None = Field(default=None, max_length=300)
    agent_token: str | None = Field(default=None, description="传 null 清除")
    description: str | None = None
    enabled: bool | None = None


class WorkerContainerInfo(SQLModel):
    """worker 容器实时状态(agent docker 采集 + 心跳/inspect 关联)"""

    id: str = Field(description="容器短 ID")
    name: str = Field(description="容器名")
    hostname: str | None = Field(default=None, description="容器内 hostname(心跳匹配键)")
    state: str = Field(default="unknown", description="容器状态(running/exited/...)")
    status: str = Field(default="", description="状态描述(Up 2 hours 等)")
    started_at: str | None = Field(default=None, description="启动时间(ISO)")
    # ---- 关联的 celery worker(按 hostname 匹配心跳, 未匹配为 None) ----
    worker_name: str | None = Field(default=None, description="对应 celery 节点名")
    worker_ip: str | None = Field(default=None)
    worker_active: int = Field(default=0, description="在途任务数")
    worker_queues: list[str] = Field(default_factory=list)


class WorkerHostView(SQLModel):
    """worker 宿主机聚合视图(注册表 JOIN agent 容器实时状态)"""

    id: str
    host_name: str
    agent_url: str
    description: str | None = None
    enabled: bool
    has_token: bool = Field(default=False, description="是否配置 token(不回传明文)")
    reachable: bool = Field(default=False, description="agent 是否可达")
    error: str | None = Field(default=None, description="agent 不可达原因")
    containers: list[WorkerContainerInfo] = Field(default_factory=list)
    running: int = Field(default=0, description="运行中容器数")
    total: int = Field(default=0, description="容器总数(含已退出)")


class WorkerScaleOpView(SQLModel):
    """副本伸缩操作状态(缩容为后台任务, 前端轮询闭环)"""

    op_id: str
    host_id: str
    host_name: str
    from_count: int
    to_count: int
    phase: str = Field(description="checking/draining/waiting_stable/scaling/done/failed/aborted")
    message: str | None = Field(default=None, description="当前阶段说明/失败原因")
    created_at: str
    updated_at: str


class TaskRecoverResponse(SQLModel):
    """手动自愈结果(重派发遗留 PENDING + 清扫僵尸 RUNNING)"""

    recovered: int = Field(default=0, description="重派发的遗留任务数")
    reaped: int = Field(default=0, description="清扫归档的僵尸任务数")


class TaskRegistryResponse(SQLModel):
    """任务类型注册表响应"""

    types: list[TaskTypeDef]
