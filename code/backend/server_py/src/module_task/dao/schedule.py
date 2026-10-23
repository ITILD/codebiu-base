"""任务队列模块 task_schedule 数据访问层(REQ-012 周期调度)"""

from datetime import datetime

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from common.utils.fastapi_ex.exceptions import NotFoundError
from common.utils.db.schema.pagination import PaginationParams
from module_task.do.schedule import TaskSchedule


class TaskScheduleDao:
    @DaoRel
    async def add(self, data: TaskSchedule, session: AsyncSession | None = None) -> int:
        """新增调度定义 :return: 自增主键"""
        session.add(data)
        await session.flush()
        return data.id  # type: ignore[return-value]

    @DaoRel
    async def get(self, schedule_id: int, session: AsyncSession | None = None) -> TaskSchedule | None:
        """按ID查询调度"""
        return await session.get(TaskSchedule, schedule_id)

    @DaoRel
    async def get_by_name(
        self, name: str, session: AsyncSession | None = None
    ) -> TaskSchedule | None:
        """按名称查询(启动播种幂等去重)"""
        statement = select(TaskSchedule).where(TaskSchedule.name == name)
        return (await session.exec(statement)).first()

    @DaoRel
    async def update(self, data: TaskSchedule, session: AsyncSession | None = None) -> None:
        """保存调度对象变更(service 修改字段后传入)"""
        session.add(data)
        await session.flush()

    @DaoRel
    async def delete(self, schedule_id: int, session: AsyncSession | None = None) -> None:
        """删除调度定义"""
        obj = await session.get(TaskSchedule, schedule_id)
        if not obj:
            raise NotFoundError(f"未找到ID为 {schedule_id} 的调度")
        await session.delete(obj)
        await session.flush()

    @DaoRel
    async def list_page(
        self,
        pagination: PaginationParams,
        session: AsyncSession | None = None,
        keyword: str | None = None,
        enabled: bool | None = None,
        task_type: str | None = None,
    ) -> list[TaskSchedule]:
        """分页查询调度列表(创建时间倒序)"""
        statement = select(TaskSchedule)
        conditions = []
        if keyword:
            conditions.append(TaskSchedule.name.contains(keyword))
        if enabled is not None:
            conditions.append(TaskSchedule.enabled == enabled)
        if task_type:
            conditions.append(TaskSchedule.task_type == task_type)
        if conditions:
            statement = statement.where(*conditions)
        statement = (
            statement.order_by(TaskSchedule.id.desc()).offset(pagination.offset).limit(pagination.limit)
        )
        return list((await session.exec(statement)).all())

    @DaoRel
    async def count(
        self,
        session: AsyncSession | None = None,
        keyword: str | None = None,
        enabled: bool | None = None,
        task_type: str | None = None,
    ) -> int:
        """统计调度总数(与列表过滤条件一致)"""
        conditions = []
        if keyword:
            conditions.append(TaskSchedule.name.contains(keyword))
        if enabled is not None:
            conditions.append(TaskSchedule.enabled == enabled)
        if task_type:
            conditions.append(TaskSchedule.task_type == task_type)
        statement = select(func.count()).select_from(TaskSchedule)
        if conditions:
            statement = statement.where(*conditions)
        return (await session.exec(statement)).one()

    @DaoRel
    async def due_schedules(
        self, now: datetime, limit: int = 20, session: AsyncSession | None = None
    ) -> list[TaskSchedule]:
        """
        查询到期待触发的调度(调度器 tick 主查询, 走 enabled+next_fire_at 复合索引)
        :param now: 当前时刻(UTC)
        :param limit: 单轮最多取数(防积压雪崩: 大量到期时分轮推进, 下轮继续)
        """
        statement = (
            select(TaskSchedule)
            .where(TaskSchedule.enabled == True, TaskSchedule.next_fire_at <= now)  # noqa: E712
            .order_by(TaskSchedule.next_fire_at)
            .limit(limit)
        )
        return list((await session.exec(statement)).all())

    @DaoRel
    async def earliest_next_fire(
        self, session: AsyncSession | None = None
    ) -> datetime | None:
        """最近一次未来触发时刻(local 调度循环据此计算休眠时长, None=无启用中调度)"""
        statement = (
            select(func.min(TaskSchedule.next_fire_at))
            .where(TaskSchedule.enabled == True)  # noqa: E712
        )
        return (await session.exec(statement)).one()
