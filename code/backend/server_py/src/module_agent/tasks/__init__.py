"""智能体模块任务接入(REQ-018): SkillRuntime 的 Task Executor 入口(入口③)

架构约定(与 module_rag/tasks 同模式):
    - 任务函数是"异步启动器": 读 task_queue payload → 回调 SkillRuntime/AgentJobService
      —— worker 不实现业务, 业务一律在 Skill 实现与领域 Service 中(CA-04)
    - 本包导入即向 module_task 的 TASK_TYPES 注册两个任务类型:
        skill_execute     queued Skill 调用(skill_invocation.task_id 双向关联)
        agent_job_execute static_agent 批处理 job(agent_job_run.task_id 关联)
"""

import logging

from common.config.tasks import app as celery_app
from module_task.do.task import QueueTaskStatus, TaskTypeDef
from module_task.tasks import TASK_TYPES, load_task, run_async, update_task_fields

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="module_agent.tasks.skill_execute_task",
    max_retries=0,  # 重试语义由 error_class 决定(§3.4), 不走 Celery 盲重试
)
def skill_execute_task(self, task_id: str):
    """queued Skill 调用执行器: 领取后回调同一 SkillRuntime(三入口殊途同归)"""
    request_id = self.request.id
    return run_async(_run_skill_execute(task_id, request_id))


async def _run_skill_execute(task_id: str, request_id: str | None) -> dict:
    from module_agent.service.skill_runtime import SkillRuntime

    payload, _user_id = await load_task(task_id)
    invocation_id: str = str(payload.get("invocation_id") or "")
    if not invocation_id:
        raise ValueError(f"任务 {task_id} payload 缺少 invocation_id")

    await update_task_fields(
        task_id, status=QueueTaskStatus.RUNNING, message="Skill 执行中", set_started=True
    )
    envelope = await SkillRuntime().execute_queued(invocation_id, task_id)
    # execute_queued 已回写 task 终态与 skill_invocation 观测, 此处返回摘要供结果后端对照
    return {
        "invocation_id": envelope.get("invocation_id"),
        "status": envelope.get("status"),
        "degraded": envelope.get("degraded"),
    }


@celery_app.task(
    bind=True,
    name="module_agent.tasks.agent_job_execute_task",
    max_retries=0,
)
def agent_job_execute_task(self, task_id: str):
    """static_agent 批处理 job 执行器(kb_ingest 等)"""
    request_id = self.request.id
    return run_async(_run_agent_job_execute(task_id, request_id))


async def _run_agent_job_execute(task_id: str, request_id: str | None) -> dict:
    from module_agent.service.agent_job import AgentJobService

    payload, _user_id = await load_task(task_id)
    job_run_id: str = str(payload.get("job_run_id") or "")
    if not job_run_id:
        raise ValueError(f"任务 {task_id} payload 缺少 job_run_id")
    return await AgentJobService().resume(job_run_id, task_id)


# ################ 任务类型注册(导入即生效; app_task.py 需 import 本包) ################

TASK_TYPES.setdefault(
    "skill_execute",
    TaskTypeDef(
        type="skill_execute",
        name="能力平台: Skill 执行",
        description="queued 形态的 Skill 调用(SkillRuntime 统一执行, 三入口共用)",
        celery_task="module_agent.tasks.skill_execute_task",
        default_payload={"invocation_id": ""},
    ),
)
TASK_TYPES.setdefault(
    "agent_job_execute",
    TaskTypeDef(
        type="agent_job_execute",
        name="能力平台: Agent job 执行",
        description="static_agent 固定工作流批处理(如知识库文档入库编排)",
        celery_task="module_agent.tasks.agent_job_execute_task",
        default_payload={"job_run_id": ""},
    ),
)
