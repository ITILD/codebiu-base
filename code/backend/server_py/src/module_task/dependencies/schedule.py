"""任务队列模块 周期调度 FastAPI 依赖注入(REQ-012)"""

from fastapi import Depends

from module_task.dao.schedule import TaskScheduleDao
from module_task.dao.task import TaskQueueDao
from module_task.service.schedule import TaskScheduleService
from module_task.service.task import TaskQueueService


async def get_task_schedule_dao() -> TaskScheduleDao:
    """周期调度DAO工厂"""
    return TaskScheduleDao()


async def get_task_schedule_service(
    dao: TaskScheduleDao = Depends(get_task_schedule_dao),
) -> TaskScheduleService:
    """周期调度Service工厂(内部组合任务队列服务复用创建/派发链路)"""
    return TaskScheduleService(dao, TaskQueueService(TaskQueueDao()))
