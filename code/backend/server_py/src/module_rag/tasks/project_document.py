"""
知识库文档解析任务(经 module_task 统一任务队列接入, local/celery 双引擎共用执行主体)

架构约定:
    - 各业务模块 controller/服务 通过 TaskQueueService.create() 创建任务并派发,
      消息只传 task_queue 表主键(task_id), 业务参数从库中读取(payload)
    - 任务函数仅是"异步启动器": 读参数 → 调用本模块功能服务(ProjectDocumentService) → 回写状态
      - celery 引擎: app_task.py worker 经 reparse_document_task → run_async 常驻循环执行
      - local 引擎: API 进程内经 run_reparse_local 直接后台协程执行
    - 进度双写: PostgreSQL task_queue 表(update_task_fields, 事实来源) +
      Celery 结果后端(update_state, 对照; local 引擎下无 Celery 上下文仅写表)
    - worker 内禁止 asyncio.run(asyncpg 连接池与循环绑定), 统一使用 run_async 常驻循环
"""
import logging

from common.config.tasks import app as celery_app
from module_task.do.task import QueueTaskStatus
from module_task.tasks import load_task, run_async, update_task_fields

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="module_rag.tasks.project_document.reparse_document_task",
    max_retries=3,
)
def reparse_document_task(self, task_id: str):
    """
    文档解析 Celery 任务(异步启动器)
    :param task_id: task_queue 表主键(payload: document_id/force_preset_id; 创建者 user_id 用于取其绑定模型)
    """
    # request 为线程本地对象, 必须在 Celery 工作线程内先捕获 ID
    request_id = self.request.id
    return run_async(_run_reparse(self, task_id, request_id))


async def run_reparse_local(task_id: str) -> dict:
    """
    文档解析 local 引擎入口(FastAPI 进程内后台协程): 复用与 Celery 完全相同的执行主体
    (由 module_task.tasks.dispatch_task 经 TASK_TYPES.local_runner 动态导入调用)
    :param task_id: task_queue 表主键
    """
    return await _run_reparse(None, task_id, None)


async def _build_document_service():
    """任务侧手动组装 ProjectDocumentService(与 dependencies/project_document 注入工厂同链路)

    修复: worker 上下文无 FastAPI Depends, 裸 ProjectDocumentService() 缺
    document_dao/project_dao 必填参数, 后台协程异常被吞导致任务永远停在 pending
    """
    from module_ai.dependencies.llm import get_llm_service
    from module_ai.dependencies.model_config import get_model_config_dao
    from module_ai.service.model_config import ModelConfigService
    from module_file.dependencies.filesystem import (
        get_file_content_dao,
        get_file_entry_dao,
    )
    from module_file.service.filesystem import FileService
    from module_office.dependencies.document_chunk import (
        get_document_chunk_prompt,
        get_document_chunk_service,
    )
    from module_office.dependencies.document_parse import get_document_parse_service
    from module_rag.dependencies.project import get_project_dao
    from module_rag.dependencies.project_document import get_project_document_dao
    from module_rag.dependencies.user_model import get_user_model_dao
    from module_rag.dao.project_document_chunk import ProjectDocumentChunkDao
    from module_rag.service.project_document import ProjectDocumentService
    from module_rag.service.project_document_chunk import ProjectDocumentChunkService
    from module_rag.service.user_model import UserModelService

    llm_service = get_llm_service()
    user_model_service = UserModelService(await get_user_model_dao(), llm_service)
    return ProjectDocumentService(
        await get_project_document_dao(),   # document_dao
        await get_project_dao(),            # project_dao
        user_model_service,                 # 用户绑定模型解析(未绑定回退公共模型)
        llm_service,
        ModelConfigService(await get_model_config_dao()),
        get_document_parse_service(),       # module_office 解析(mineru, 惰性)
        get_document_chunk_service(get_document_chunk_prompt()),  # module_office 分块(惰性)
        ProjectDocumentChunkService(
            ProjectDocumentChunkDao(), user_model_service
        ),
        FileService(await get_file_entry_dao(), await get_file_content_dao()),
    )


async def _run_reparse(celery_task, task_id: str, request_id: str | None) -> dict:
    """解析任务主体: 读参数 → 以创建者身份复检权限 → 调功能服务(带进度回调) → 双写进度状态"""
    from module_rag.dependencies.permission import enforce_project_permission
    from module_rag.service.project_document import ProjectDocumentService

    # 1. 读任务参数与创建者(模型按创建者绑定解析, worker 侧无法从请求上下文获取)
    payload, user_id = await load_task(task_id)
    document_id: str = str(payload.get("document_id") or "")
    force_preset_id = payload.get("force_preset_id") or None
    if not document_id:
        raise ValueError(f"任务 {task_id} payload 缺少 document_id")

    # 2. 执行时权限复检: 以任务创建者身份实时校验项目文档编辑权限
    #    (权限回收后任务安全失败, 不越权续跑; 直跑路径已在 controller 校验, 此处双检无害)
    document_service = await _build_document_service()
    document = await document_service.get_document(document_id)
    if document is None:
        raise ValueError(f"任务 {task_id} 指向的文档 {document_id} 不存在")
    await enforce_project_permission(user_id, document.project_id, "doc", "update")

    await update_task_fields(
        task_id, status=QueueTaskStatus.RUNNING,
        progress=0, message="开始解析文档", set_started=True,
    )

    # 3. 入库进度回调: 文档流水线步骤推进时, 把总进度/阶段描述双写到
    #    task_queue 表与 Celery 结果后端(任务模块只收百分比与描述, 不感知业务步骤;
    #    local 引擎下 celery_task 为 None, 仅写表)
    async def _on_ingest_progress(overall: float, message: str):
        await update_task_fields(task_id, progress=overall, message=message)
        if celery_task is not None:
            celery_task.update_state(
                task_id=request_id, state="PROGRESS",
                meta={"progress": overall, "message": message},
            )

    try:
        # 4. 调用功能服务执行核心逻辑(解析→分块→向量化→入库, 内部维护
        #    document.parse_status 与 parse_steps 步骤进度)
        result = await document_service.parse_document(
            document_id, user_id, progress_callback=_on_ingest_progress
        )
        result_payload = {"document_id": document_id, "success": bool(result)}

        # 5. 成功收尾(双写)
        await update_task_fields(
            task_id, status=QueueTaskStatus.SUCCESS, progress=100,
            message="解析完成", result=result_payload, set_finished=True,
        )
        if celery_task is not None:
            celery_task.update_state(
                task_id=request_id, state="SUCCESS", meta={"progress": 100},
            )
        return result_payload
    except Exception as exc:
        # 失败收尾(parse_document 内部已把 document.parse_status 置 failed, 此处只管任务表)
        logger.error(f"解析任务失败 task_id={task_id} document_id={document_id}: {exc}", exc_info=True)
        await update_task_fields(
            task_id, status=QueueTaskStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}", set_finished=True,
        )
        raise
