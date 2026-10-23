"""任务队列模块 task_schedule 表模型与请求/响应体定义(REQ-012 周期调度)"""

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlmodel import Field, SQLModel

from module_task.utils.cron import CRON_PRESETS


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskSchedule(SQLModel, table=True):
    """周期调度定义表(调度器每分钟扫描启停状态与下次触发时刻, 修改即时热生效)

    触发方式二选一: cron 表达式(5 字段) / interval_seconds 固定间隔(秒);
    执行历史不建关联表(防膨胀): 触发即向 task_queue 写一条记录并回写最近一次执行快照,
    完整历史在任务队列页按任务类型筛选查看。
    """

    __tablename__ = "task_schedule"
    __table_args__ = (
        # 调度器扫描路径: 只取 enabled 且到期的行(每轮少量), 无全表扫描
        Index("ix_task_schedule_enabled_next", "enabled", "next_fire_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, index=True, description="调度名称(触发产生的任务沿用)")
    task_type: str = Field(
        max_length=50, description="任务类型(TASK_TYPES 注册表编码, 如 sys_audit_purge)"
    )
    payload: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
        description="任务参数 JSON(与手工创建任务同构, 触发时原样带入)",
    )
    # ---- 触发方式(cron 优先, 二者至少其一) ----
    cron: str | None = Field(
        default=None,
        sa_column=Column(String(50)),
        description="5 字段 cron 表达式(分 时 日 月 周), 与 interval_seconds 二选一",
    )
    interval_seconds: int | None = Field(
        default=None,
        sa_column=Column(Integer),
        description="固定触发间隔(秒, ≥60 与 cron 二选一; 每 N 秒触发一次)",
    )
    enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
        description="启停(停用时调度器跳过, 开启时按定义重算下次触发)",
    )
    # ---- 触发簿记(最近一次快照, 完整历史见 task_queue) ----
    next_fire_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="下次触发时刻(UTC; 创建/启停/改周期时重算)",
    )
    last_fired_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True)), description="最近触发时刻"
    )
    last_task_id: str | None = Field(
        default=None, max_length=64, description="最近触发生成的任务ID(跳转任务详情)"
    )
    last_status: str | None = Field(
        default=None, max_length=20, description="最近触发时任务入队结果(ok/dispatch_failed)"
    )
    remark: str | None = Field(default=None, sa_column=Column(Text), description="备注说明")
    created_by: str = Field(index=True, description="创建者用户ID(触发任务的执行身份)")
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), onupdate=_utcnow, nullable=False),
    )


class TaskScheduleCreate(SQLModel):
    """创建调度请求"""

    name: str = Field(max_length=200, description="调度名称")
    task_type: str = Field(max_length=50, description="任务类型(需在 TASK_TYPES 注册表中)")
    payload: dict = Field(default_factory=dict, description="任务参数 JSON")
    cron: str | None = Field(None, max_length=50, description="cron 表达式(与 interval 二选一)")
    interval_seconds: int | None = Field(None, description="触发间隔秒(≥60, 与 cron 二选一)")
    enabled: bool = Field(False, description="创建后是否立即启用")
    remark: str | None = Field(None, description="备注")


class TaskScheduleUpdate(SQLModel):
    """修改调度请求(全量字段; 启停/改周期后热生效)"""

    name: str = Field(max_length=200)
    task_type: str = Field(max_length=50)
    payload: dict = Field(default_factory=dict)
    cron: str | None = None
    interval_seconds: int | None = None
    enabled: bool = False
    remark: str | None = None


class TaskScheduleResponse(SQLModel):
    """调度详情响应(前端定时任务页)"""

    id: int
    name: str
    task_type: str
    payload: dict
    cron: str | None = None
    interval_seconds: int | None = None
    enabled: bool
    next_fire_at: datetime | None = None
    last_fired_at: datetime | None = None
    last_task_id: str | None = None
    last_status: str | None = None
    remark: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class TaskScheduleTriggerResult(SQLModel):
    """手动立即触发结果"""

    task_id: str
    schedule_id: int


# 触发方式约束(与 do 层校验共用)
MIN_INTERVAL_SECONDS = 60

# cron 快捷预置(响应给前端渲染快捷选项)
CRON_PRESET_LIST: list[dict[str, str]] = [
    {"key": key, "expr": expr} for key, expr in CRON_PRESETS.items()
]

# 触发方式字面量(类型提示用)
ScheduleKind = Literal["cron", "interval"]
