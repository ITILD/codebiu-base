"""任务队列模块 task FastAPI 依赖注入"""

from fastapi import Depends

from module_task.dao.task import TaskQueueDao
from module_task.service.queue_registry import TaskQueueRegistryService
from module_task.service.task import TaskQueueService
from module_task.service.worker_host import WorkerHostService


async def get_task_queue_dao() -> TaskQueueDao:
    """任务队列DAO工厂"""
    return TaskQueueDao()


async def get_task_queue_service(
    dao: TaskQueueDao = Depends(get_task_queue_dao),
) -> TaskQueueService:
    """任务队列Service工厂"""
    return TaskQueueService(dao)


async def get_queue_registry_service(
    dao: TaskQueueDao = Depends(get_task_queue_dao),
) -> TaskQueueRegistryService:
    """队列注册表Service工厂"""
    return TaskQueueRegistryService(dao)


async def get_worker_host_service(
    dao: TaskQueueDao = Depends(get_task_queue_dao),
) -> WorkerHostService:
    """worker 宿主机运维Service工厂"""
    return WorkerHostService(dao)
