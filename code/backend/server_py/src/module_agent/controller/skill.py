"""能力平台 API(REQ-018, 三入口之① Web 手动触发)

- POST /agent/skills/{key}/invoke  Skill 调试台(直调任意 Skill, mode 可指定;
  默认不授予, 仅管理员/调试场景 —— 对话入口不经此端点)
- GET  /agent/invocations[/...]    调用观测查询(三入口全量可追溯)
- GET  /agent/jobs                 job Agent 清单(static_agent Manifest)
- POST /agent/jobs/{key}/submit    job 提交(如整库入库编排)
- GET  /agent/job-runs/{id}        job 运行详情(步骤状态/when/skip_if 判定)
"""

import logging

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import case, func
from sqlmodel import desc, select

from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_agent.service.agent_job import AgentJobService
from module_agent.service.skill_runtime import SkillContext, SkillRuntime
from module_agent.do.skill import SkillInvocation
from module_authorization.dependencies.permission import (
    get_current_user_id,
    require_permission,
)
from common.config.db import db_manager
from common.utils.fastapi_ex.exceptions import ForbiddenError, NotFoundError

from module_agent.config.server import module_app

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/skills/{skill_key}/invoke", summary="调用 Skill(调试台)")
async def invoke_skill(
    skill_key: str,
    body: dict,
    current_user_id: str = Depends(
        require_permission("agent", "skill", "invoke")
    ),
) -> dict:
    """直接调起任意 Skill(统一走 SkillRuntime; 三入口殊途同归可追溯)

    :param skill_key: Skill 全局键(sys.doc_parse)
    :param body: {input: {...}, mode?: auto/inline/queued}
    :return: 统一信封 {invocation_id, skill_key, mode, status, task_id, result, error, ...}
    """
    skill_input = dict(body.get("input") or {})
    mode = str(body.get("mode") or "auto")
    envelope = await SkillRuntime().invoke(
        skill_key,
        skill_input,
        SkillContext(user_id=current_user_id, entry="debug"),
        mode=mode,
    )
    return envelope


@router.get("/invocations/{invocation_id}", summary="查询 Skill 调用详情")
async def get_invocation(
    invocation_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    """按 ID 查调用记录(本人可查; 输出为大字段截断后的观测口径)"""
    invocation = await SkillRuntime().get_invocation(invocation_id)
    if invocation is None:
        raise NotFoundError(f"调用记录不存在: {invocation_id}")
    if invocation.user_id != current_user_id:
        raise ForbiddenError("仅可查询本人的调用记录")
    return {
        "invocation_id": invocation.invocation_id,
        "skill_key": invocation.skill_key,
        "skill_version": invocation.skill_version,
        "mode": invocation.mode,
        "status": invocation.status,
        "degraded": invocation.degraded,
        "priority_class": invocation.priority_class,
        "idempotency_key": invocation.idempotency_key,
        "input_summary": invocation.input_summary.get("idempotency_fields"),
        "output": invocation.output,
        "error_class": invocation.error_class,
        "error_message": invocation.error_message,
        "duration_ms": invocation.duration_ms,
        "tokens": invocation.tokens,
        "task_id": invocation.task_id,
        "entry": invocation.entry,
        "started_at": invocation.started_at,
        "finished_at": invocation.finished_at,
    }


@router.get("/invocations", summary="分页查询 Skill 调用记录")
async def list_invocations(
    pagination: PaginationParams = Depends(),
    skill_key: str | None = None,
    status_filter: str | None = None,
    current_user_id: str = Depends(get_current_user_id),
) -> PaginationResponse:
    """本人调用记录分页(观测台数据源; 管理端全量视图后续批次)"""
    async with db_manager.db_rel.session_factory() as session:
        where = [SkillInvocation.user_id == current_user_id]
        if skill_key:
            where.append(SkillInvocation.skill_key == skill_key)
        if status_filter:
            where.append(SkillInvocation.status == status_filter)
        total = await session.scalar(
            select(func.count()).select_from(SkillInvocation).where(*where)
        )
        rows = (
            await session.exec(
                select(SkillInvocation)
                .where(*where)
                .order_by(desc(SkillInvocation.created_at))
                .offset((pagination.page - 1) * pagination.size)
                .limit(pagination.size)
            )
        ).all()
        items = [
            {
                "invocation_id": r.invocation_id,
                "skill_key": r.skill_key,
                "mode": r.mode,
                "status": r.status,
                "degraded": r.degraded,
                "error_class": r.error_class,
                "duration_ms": r.duration_ms,
                "task_id": r.task_id,
                "entry": r.entry,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    return PaginationResponse.create(items=items, total=int(total or 0), pagination=pagination)


@router.get("/jobs", summary="job Agent 清单")
async def list_jobs(_: str = Depends(get_current_user_id)) -> list[dict]:
    """内置 job Agent(static_agent)清单: 步骤声明/条件/资源策略"""
    from module_agent.agents import list_agent_jobs

    return [
        {
            "agent_key": m.agent_key,
            "name": m.name,
            "description": m.description,
            "agent_kind": m.agent_kind,
            "decision_mode": m.decision_mode,
            "version": m.version,
            "steps": [s.model_dump() for s in m.steps],
            "runtime_policy": m.runtime_policy,
        }
        for m in list_agent_jobs()
    ]


# ################ 自定义 prompt Skill(REQ-018 批次 2) ################


@router.get("/skills/custom", summary="自定义 Skill 列表(prompt)")
async def list_custom_skills(
    current_user_id: str = Depends(get_current_user_id),
) -> list[dict]:
    """本人创建的自定义 Skill(管理员见全量); draft/published/deprecated 状态机"""
    from module_agent.service.prompt_skill import PromptSkillService

    return await PromptSkillService().list_custom(current_user_id)


@router.get("/skills/custom/{skill_id}", summary="自定义 Skill 详情(编辑回显)")
async def get_custom_skill(
    skill_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    """最新版本快照回显: 模板原文/字段声明/输出格式(编辑表单数据源)"""
    from module_agent.service.prompt_skill import PromptSkillService

    return await PromptSkillService().get_detail(skill_id, current_user_id)


@router.post("/skills/custom", summary="创建自定义 Skill(prompt, 草稿)")
async def create_custom_skill(
    body: dict,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    """创建 prompt Skill 草稿(usr 命名空间; 发布后方注册可调用)"""
    from module_agent.service.prompt_skill import PromptSkillCreate, PromptSkillService

    req = PromptSkillCreate(**body)
    return await PromptSkillService().create(req, current_user_id)


@router.put("/skills/custom/{skill_id}", summary="更新自定义 Skill")
async def update_custom_skill(
    skill_id: str,
    body: dict,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    """更新模板/字段(已发布则生成新版本快照并重注册生效)"""
    from module_agent.service.prompt_skill import PromptSkillService, PromptSkillUpdate

    return await PromptSkillService().update(
        skill_id, PromptSkillUpdate(**body), current_user_id
    )


@router.post("/skills/custom/{skill_id}/publish", summary="发布自定义 Skill")
async def publish_custom_skill(
    skill_id: str,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    from module_agent.service.prompt_skill import PromptSkillService

    return await PromptSkillService().publish(skill_id, current_user_id)


@router.delete("/skills/custom/{skill_id}", summary="下线自定义 Skill")
async def deprecate_custom_skill(
    skill_id: str,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    """下线(注册表反注册, 新调用被拒; 历史调用记录保留可追溯)"""
    from module_agent.service.prompt_skill import PromptSkillService

    return await PromptSkillService().deprecate(skill_id, current_user_id)


# ################ Skill Hub / MCP / 用量(REQ-018 批次 3) ################


@router.get("/skill-hub/packages", summary="已导入社区包清单")
async def list_skill_hub_packages(
    _: str = Depends(get_current_user_id),
) -> list[dict]:
    """Skill Hub 包清单(pack.* 命名空间, 拆解产物与注册状态)"""
    from module_agent.service.skill_hub import SkillHubService

    return await SkillHubService().list_packages()


@router.post("/skill-hub/packages", summary="导入社区 SKILL.md 包(zip)")
async def import_skill_hub_package(
    file: UploadFile,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    """上传 zip(SKILL.md + scripts/ + references/) → 拆解注册:
    指令 → pack.{包名}.main(prompt); 脚本 → pack.{包名}.{名}(script 沙箱)"""
    from module_agent.service.skill_hub import SkillHubService

    zip_bytes = await file.read()
    return await SkillHubService().import_package(zip_bytes, current_user_id)


@router.delete("/skill-hub/packages/{namespace}", summary="删除社区包")
async def remove_skill_hub_package(
    namespace: str,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    from module_agent.service.skill_hub import SkillHubService

    return await SkillHubService().remove_package(namespace, current_user_id)


@router.get("/mcp/servers", summary="已登记 MCP server 清单")
async def list_mcp_servers(
    _: str = Depends(get_current_user_id),
) -> list[dict]:
    from module_agent.service.mcp_adapter import McpServerService

    return await McpServerService().list_servers()


@router.post("/mcp/servers", summary="登记 MCP server(stdio)并反射注册 tools")
async def register_mcp_server(
    body: dict,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    """{name, command, args?, env?} → 连接验证 + tools/list 反射注册为
    mcp.{name}.{tool} Skill(mcp_tool 类型, 三入口一致可追溯)"""
    from module_agent.service.mcp_adapter import McpServerService

    return await McpServerService().register(body, current_user_id)


@router.delete("/mcp/servers/{namespace}", summary="移除 MCP server")
async def remove_mcp_server(
    namespace: str,
    current_user_id: str = Depends(require_permission("agent", "skill", "update")),
) -> dict:
    from module_agent.service.mcp_adapter import McpServerService

    return await McpServerService().remove(namespace)


@router.get("/usage/summary", summary="用量与计费口径汇总(双粒度)")
async def usage_summary(
    days: int = 30,
    current_user_id: str = Depends(require_permission("agent", "skill", "read")),
) -> dict:
    """计费口径 = skill_invocation + agent_job_run 双粒度聚合(§9 批次 3 验收):
    按 Skill 的调用量/成功率/降级数/tokens/时长 + 按 job 的运行量/成功率"""
    from datetime import datetime, timedelta, timezone

    from module_agent.do.agent_job_run import AgentJobRun

    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=min(max(days, 1), 365))
    async with db_manager.db_rel.session_factory() as session:
        skill_rows = (
            await session.exec(
                select(
                    SkillInvocation.skill_key,
                    func.count().label("calls"),
                    func.sum(case((SkillInvocation.status == "succeeded", 1), else_=0)).label("succeeded"),
                    func.sum(case((SkillInvocation.degraded.is_(True), 1), else_=0)).label("degraded"),
                    func.coalesce(func.sum(SkillInvocation.tokens), 0).label("tokens"),
                    func.coalesce(func.sum(SkillInvocation.duration_ms), 0).label("duration_ms"),
                )
                .where(SkillInvocation.created_at >= since)
                .group_by(SkillInvocation.skill_key)
                .order_by(func.count().desc())
            )
        ).all()
        job_rows = (
            await session.exec(
                select(
                    AgentJobRun.agent_key,
                    func.count().label("runs"),
                    func.sum(case((AgentJobRun.status == "succeeded", 1), else_=0)).label("succeeded"),
                )
                .where(AgentJobRun.created_at >= since)
                .group_by(AgentJobRun.agent_key)
            )
        ).all()
    return {
        "since": since.isoformat(),
        "by_skill": [dict(r._mapping) for r in skill_rows],
        "by_agent_job": [dict(r._mapping) for r in job_rows],
    }


@router.post("/jobs/{agent_key}/submit", summary="提交 job Agent 运行")
async def submit_job(
    agent_key: str,
    body: dict,
    current_user_id: str = Depends(
        require_permission("agent", "skill", "invoke")
    ),
) -> dict:
    """提交 job(默认 queued; 小批量可 body.mode=inline)

    :param body: {input: {...}, mode?: auto/inline}  如 input={documents: [{document_id}]}
    """
    job_input = dict(body.get("input") or {})
    mode = str(body.get("mode") or "auto")
    return await AgentJobService().submit(
        agent_key,
        job_input,
        SkillContext(user_id=current_user_id, entry="web"),
        mode=mode,
    )


@router.post("/job-runs/{job_run_id}/resume", summary="断点续跑失败的 job")
async def resume_job_run(
    job_run_id: str,
    current_user_id: str = Depends(require_permission("agent", "skill", "invoke")),
) -> dict:
    """断点续跑(REQ-018 批次 2): 已成功项直接复用, 产物经 checkpoint 恢复,
    从失败/取消位置继续执行(仅失败/取消态可续)"""
    return await AgentJobService().resume_run(job_run_id, current_user_id)


@router.get("/job-runs", summary="分页查询 job 运行记录")
async def list_job_runs(
    pagination: PaginationParams = Depends(),
    agent_key: str | None = None,
    status_filter: str | None = None,
    current_user_id: str = Depends(get_current_user_id),
) -> PaginationResponse:
    """本人提交的 job 运行分页(job 页签运行历史数据源)"""
    from module_agent.do.agent_job_run import AgentJobRun

    async with db_manager.db_rel.session_factory() as session:
        where = [AgentJobRun.user_id == current_user_id]
        if agent_key:
            where.append(AgentJobRun.agent_key == agent_key)
        if status_filter:
            where.append(AgentJobRun.status == status_filter)
        total = await session.scalar(
            func.count().select_from(AgentJobRun).where(*where)
        )
        rows = (
            await session.exec(
                select(AgentJobRun)
                .where(*where)
                .order_by(desc(AgentJobRun.created_at))
                .offset((pagination.page - 1) * pagination.size)
                .limit(pagination.size)
            )
        ).all()
        items = [
            {
                "job_run_id": r.job_run_id,
                "agent_key": r.agent_key,
                "status": r.status,
                "progress": r.progress,
                "error": r.error,
                "task_id": r.task_id,
                "entry": r.entry,
                "created_at": r.created_at,
                "finished_at": r.finished_at,
            }
            for r in rows
        ]
    return PaginationResponse.create(items=items, total=int(total or 0), pagination=pagination)


@router.get("/job-runs/{job_run_id}", summary="查询 job 运行详情")
async def get_job_run(
    job_run_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    """job 运行详情: 进度/步骤状态(含 when/skip_if 判定结果, W-3)"""
    run = await AgentJobService().get(job_run_id)
    if run is None:
        raise NotFoundError(f"job 运行不存在: {job_run_id}")
    if run.user_id != current_user_id:
        raise ForbiddenError("仅可查询本人提交的 job")
    return {
        "job_run_id": run.job_run_id,
        "agent_key": run.agent_key,
        "agent_version": run.agent_version,
        "status": run.status,
        "progress": run.progress,
        "steps_state": run.steps_state,
        "input_summary": run.input_summary,
        "result": run.result,
        "error": run.error,
        "task_id": run.task_id,
        "entry": run.entry,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
    }


module_app.include_router(router, tags=["能力平台"])
