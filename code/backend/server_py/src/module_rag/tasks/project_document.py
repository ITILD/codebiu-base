"""知识库文档解析入库任务(REQ-013 → REQ-018 能力平台化)

任务体是薄启动器: 领取后经 kb_ingest_agent(static_agent)编排
doc_parse → doc_chunk_index 两个 Skill —— 与页面/对话入口共用同一
SkillRuntime 实现(CA-04), 全程可在 skill_invocation/agent_job_run 追溯。
"""

import logging

from common.config.tasks import app as celery_app
from module_task.tasks import load_task, run_async, update_task_fields

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="module_rag.tasks.reparse_document_task",
    max_retries=0,
)
def reparse_document_task(self, task_id: str):
    """单文档解析入库(worker 内直跑 kb_ingest job, 不嵌套排队)"""
    return run_async(_run_ingest(task_id))


@celery_app.task(
    bind=True,
    name="module_rag.tasks.reparse_project_documents",
    max_retries=0,
)
def reparse_project_documents(self, task_id: str):
    """整库文档重新解析入库(单 job fan_out 全量文档)"""
    return run_async(_run_ingest(task_id))


async def _run_ingest(task_id: str) -> dict:
    """领取任务 → 组装 kb_ingest job 输入 → worker 内直跑(inline)"""
    from module_agent.service.agent_job import AgentJobService
    from module_agent.service.skill_runtime import SkillContext
    from module_rag.dao.project_document import ProjectDocumentDao

    payload, user_id = await load_task(task_id)
    await update_task_fields(
        task_id, status="running", message="组装入库编排", set_started=True
    )

    documents = [{"document_id": str(document_id)} for document_id in _collect_documents(payload)]
    if not documents:
        await update_task_fields(
            task_id, status="success", progress=100, message="无可解析文档",
            set_finished=True,
        )
        return {"status": "succeeded", "steps": {}}

    outcome = await AgentJobService().submit(
        "sys.kb_ingest_agent",
        {"documents": documents},
        SkillContext(user_id=user_id, priority_class="standard", entry="task"),
        mode="inline",  # 已在 worker 进程内, job 直跑避免嵌套排队
    )
    status = str(outcome.get("status"))
    if status == "succeeded":
        await update_task_fields(
            task_id, status="success", progress=100, message="解析入库完成",
            result={"job_run_id": outcome.get("job_run_id"), "steps": outcome.get("steps")},
            set_finished=True,
        )
    else:
        await update_task_fields(
            task_id, status="failed",
            error=f"入库编排未全部成功(详见 agent_job_run {outcome.get('job_run_id')})",
            set_finished=True,
        )
    return outcome


async def _collect_documents(payload: dict) -> list[str]:
    """按任务 payload 收集文档ID(document_id 单文档 / project_id 整库)"""
    document_id = payload.get("document_id")
    if document_id:
        return [str(document_id)]
    project_id = payload.get("project_id")
    if not project_id:
        return []
    from sqlalchemy import select

    from common.config.db import db_manager
    from module_rag.do.project_document import ProjectDocument

    async with db_manager.db_rel.session_factory() as session:
        rows = await session.exec(
            select(ProjectDocument.id).where(ProjectDocument.project_id == project_id)
        )
        return [str(row) for row in rows.all()]
