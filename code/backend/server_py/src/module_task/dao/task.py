"""任务队列模块 task 数据访问层"""

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from common.utils.fastapi_ex.exceptions import NotFoundError
from common.utils.db.schema.pagination import PaginationParams
from module_task.do.task import TaskQueue, TaskQueueResponse, TaskTypePriority


class TaskQueueDao:
    @DaoRel
    async def add(
        self, data: TaskQueue, session: AsyncSession | None = None
    ) -> str:
        """
        新增任务记录(status=pending)
        :param data: 已构造完整的任务ORM对象
        :return: 任务ID
        """
        session.add(data)
        await session.flush()
        return data.id

    @DaoRel
    async def get(
        self, task_id: str, session: AsyncSession | None = None
    ) -> TaskQueue | None:
        """按ID查询任务"""
        return await session.get(TaskQueue, task_id)

    @DaoRel
    async def update(
        self, task: TaskQueue, session: AsyncSession | None = None
    ) -> None:
        """
        保存任务对象变更(由 service 修改字段后传入)
        :param task: 已修改字段的ORM对象
        """
        session.add(task)
        await session.flush()

    @DaoRel
    async def delete(self, task_id: str, session: AsyncSession | None = None) -> None:
        """删除任务记录"""
        task = await session.get(TaskQueue, task_id)
        if not task:
            raise NotFoundError(f"未找到ID为 {task_id} 的任务")
        await session.delete(task)
        await session.flush()

    @DaoRel
    async def list_page(
        self,
        pagination: PaginationParams,
        session: AsyncSession | None = None,
        keyword: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        user_id: str | None = None,
        priority: int | None = None,
    ) -> list[TaskQueue]:
        """
        分页查询任务列表(创建时间倒序)
        :param keyword: 任务名称模糊匹配
        :param status: 状态精确过滤
        :param task_type: 任务类型精确过滤
        :param user_id: 创建者过滤(None 表示不过滤)
        :param priority: 优先级精确过滤
        """
        statement = select(TaskQueue)
        conditions = []
        if keyword:
            conditions.append(TaskQueue.name.contains(keyword))
        if status:
            conditions.append(TaskQueue.status == status)
        if task_type:
            conditions.append(TaskQueue.task_type == task_type)
        if user_id:
            conditions.append(TaskQueue.user_id == user_id)
        if priority is not None:
            conditions.append(TaskQueue.priority == priority)
        if conditions:
            statement = statement.where(*conditions)
        statement = (
            statement.order_by(TaskQueue.created_at.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        result = await session.exec(statement)
        return list(result.all())

    @DaoRel
    async def count(
        self,
        session: AsyncSession | None = None,
        keyword: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        user_id: str | None = None,
        priority: int | None = None,
    ) -> int:
        """统计任务总数(与列表过滤条件一致)"""
        conditions = []
        if keyword:
            conditions.append(TaskQueue.name.contains(keyword))
        if status:
            conditions.append(TaskQueue.status == status)
        if task_type:
            conditions.append(TaskQueue.task_type == task_type)
        if user_id:
            conditions.append(TaskQueue.user_id == user_id)
        if priority is not None:
            conditions.append(TaskQueue.priority == priority)
        statement = select(func.count()).select_from(TaskQueue)
        if conditions:
            statement = statement.where(*conditions)
        result = await session.exec(statement)
        return result.one()

    @DaoRel
    async def stats(
        self, session: AsyncSession | None = None
    ) -> dict[str, int]:
        """
        按状态分组统计任务数
        :return: {"pending": n, "running": n, "success": n, ...}
        """
        statement = select(TaskQueue.status, func.count()).group_by(TaskQueue.status)
        result = await session.exec(statement)
        return {row[0]: row[1] for row in result.all()}

    @DaoRel
    async def get_all_priority_overrides(
        self, session: AsyncSession | None = None
    ) -> dict[str, int]:
        """读取全部任务类型优先级覆盖 {task_type: priority_override}"""
        result = await session.exec(select(TaskTypePriority))
        return {row.task_type: row.priority_override for row in result.all()}

    @DaoRel
    async def upsert_priority_override(
        self, task_type: str, priority: int, session: AsyncSession | None = None
    ) -> None:
        """写入/更新某任务类型的入队优先级覆盖"""
        row = await session.get(TaskTypePriority, task_type)
        if row is None:
            session.add(
                TaskTypePriority(task_type=task_type, priority_override=priority)
            )
        else:
            row.priority_override = priority
            session.add(row)
        await session.flush()

    @DaoRel
    async def delete_priority_override(
        self, task_type: str, session: AsyncSession | None = None
    ) -> bool:
        """删除某任务类型的优先级覆盖(回落注册表默认值); 返回是否删除了记录"""
        row = await session.get(TaskTypePriority, task_type)
        if row is None:
            return False
        await session.delete(row)
        await session.flush()
        return True
