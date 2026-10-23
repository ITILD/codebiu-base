"""
系统维护类任务执行器(REQ-012 首个内置周期任务示例)

sys_audit_purge: 操作审计日志周期清理 —— 联动 REQ-009 审计模块,
按动态配置 audit.retention_days 清理过期记录(薄启动器模式:
读参数 → 调业务模块 service → 双写进度, 与 demo 任务同构)。
"""
import logging

from common.config.tasks import app as celery_app
from module_task.do.task import QueueTaskStatus
from module_task.tasks import run_async, update_task_fields

logger = logging.getLogger(__name__)


async def _run_purge_audit(task_id: str) -> dict:
    """审计清理主体: 直接复用审计模块 service(幂等, 可重入)"""
    await update_task_fields(
        task_id,
        status=QueueTaskStatus.RUNNING,
        progress=10,
        message="开始清理过期审计日志",
        set_started=True,
    )
    try:
        from module_main.service.audit_log import purge_expired

        deleted = await purge_expired()
        result = {"purged": deleted}
        await update_task_fields(
            task_id,
            status=QueueTaskStatus.SUCCESS,
            progress=100,
            message=f"清理完成, 删除 {deleted} 条过期记录",
            result=result,
            set_finished=True,
        )
        return result
    except Exception as exc:
        logger.exception(f"审计清理任务 {task_id} 执行失败")
        await update_task_fields(
            task_id,
            status=QueueTaskStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}",
            set_finished=True,
        )
        raise


@celery_app.task(name="module_task.tasks.maintenance.purge_audit_task")
def purge_audit_task(task_id: str) -> dict:
    """celery 引擎入口(worker 专用循环内执行)"""
    return run_async(_run_purge_audit(task_id))


async def run_purge_audit_local(task_id: str) -> dict:
    """local 引擎入口(进程内后台协程, 与 celery 共用同一执行主体)"""
    return await _run_purge_audit(task_id)
