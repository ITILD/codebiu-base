"""
module_task 任务注册表与 worker/派发辅助

设计说明(通用任务队列, Celery 单引擎):
    1. 新业务模块接入队列时, 在 TASK_TYPES 中注册一个 TaskTypeDef 条目即可:
       - celery_task: 任务在 Celery 中的路由名(与 @celery_app.task(name=...) 一致)
       - default_payload: 前端"新建任务"对话框的默认参数模板
    2. 派发(dispatch_task)统一投递 Redis broker, 由 app_task.py worker 消费执行;
       任务状态/进度/结果实时回写 PostgreSQL task_queue 表, API 侧读库展示,
       并可通过 Celery AsyncResult 读取 broker/backend 侧真实状态做对照。
    3. worker 侧通过 update_task_fields() 把 状态/百分比/阶段消息 实时回写 PostgreSQL,
    4. 任务函数统一是"薄启动器": load_task 读参数 → 调用业务模块自己的 service 执行 →
       双写进度。service 保持纯净(不抛 HTTP 异常), 复杂解析等重活一律经任务队列
       在独立 worker 进程执行, 不占用 API 进程。
    5. 任务账户与权限约定(推荐模式):
       - 账户: task_queue.user_id 记录任务创建者, worker 经 load_task 取回作为"任务身份";
       - 权限: 创建时由 controller 鉴权(require_permission / enforce_project_permission),
               执行时 worker 以 user_id 实时查库复检资源权限(casbin/项目档位),
               不快照权限 —— 权限被回收后任务安全失败, 不会越权续跑。
"""
import asyncio
import logging
import threading

from common.config.db import db_manager
from module_task.do.task import QueueTaskStatus, TaskTypeDef

logger = logging.getLogger(__name__)

# ################ worker 专用事件循环 ################
# Celery 任务函数是同步的, 每次用 asyncio.run 会创建新事件循环,
# 而 asyncpg 连接与创建它的循环绑定(跨循环复用会崩溃)。
# 因此 worker 进程启动时开一个常驻循环线程, 所有任务协程都提交到该循环执行,
# 使全局连接池(db_manager.db_rel)在进程生命周期内绑定同一个循环。

_worker_loop = asyncio.new_event_loop()
threading.Thread(target=_worker_loop.run_forever, daemon=True, name="task-worker-loop").start()


def run_async(coro):
    """
    在 worker 专用事件循环中执行协程并阻塞等待结果
    (Celery 任务函数内部用; 进程内所有任务共享循环与数据库连接池)
    """
    return asyncio.run_coroutine_threadsafe(coro, _worker_loop).result()

# ################ 任务类型注册表 ################

TASK_TYPES: dict[str, TaskTypeDef] = {
    "demo_document": TaskTypeDef(
        type="demo_document",
        name="示例: 文档处理",
        description="模拟文档处理流水线(解析→分块→向量化→入库), 用于演示任务队列全流程; "
                    "后续知识库模块的真实文档处理任务将替换此实现",
        celery_task="task.run_demo_document",
        default_payload={
            "file_name": "示例文档.pdf",
            "total_pages": 42,
            "duration": 16,
        },
    ),
    "rag_document_parse": TaskTypeDef(
        type="rag_document_parse",
        name="知识库: 文档解析",
        description="解析项目文档: OCR/解析 → 分块策略识别 → 重分块 → 向量化 → 写入向量库;"
                    "以任务创建者绑定的模型执行(未绑定时回退默认公共模型)",
        celery_task="module_rag.tasks.project_document.reparse_document_task",
        default_payload={"document_id": "", "force_preset_id": None},
    ),
    "rag_revectorize": TaskTypeDef(
        type="rag_revectorize",
        name="知识库: 全库重向量化",
        description="系统更换向量模型后, 以指定/当前生效的默认公共向量化模型"
                    "重算向量表中所有文档 chunk 向量(仅系统管理员)",
        celery_task="module_rag.tasks.project_document_chunk.revectorize_chunks_task",
        default_payload={"model_id": None},
    ),
    "sys_audit_purge": TaskTypeDef(
        type="sys_audit_purge",
        name="系统: 审计日志清理",
        description="按动态配置 audit.retention_days 周期清理过期操作审计记录"
                    "(REQ-012 内置示例, 建议每日凌晨执行; 保留期在 系统配置→操作审计 修改)",
        celery_task="module_task.tasks.maintenance.purge_audit_task",
        default_payload={},
    ),
}


def get_task_type(task_type: str) -> TaskTypeDef | None:
    """按类型编码查询注册表条目"""
    return TASK_TYPES.get(task_type)

# ################ 统一派发 ################


async def dispatch_task(task, task_def: TaskTypeDef) -> str:
    """
    统一派发入口(创建/重试/自愈共用): 投递 Redis broker, 返回 celery_task_id
    :param task: task_queue 表记录(读 id/priority)
    :param task_def: 任务类型定义
    :return: celery_task_id
    :raises Exception: 投递失败(调用方负责回写任务失败状态)
    """
    from common.config.tasks import (
        DEFAULT_QUEUE,
        INTERACTIVE_PRIORITY_THRESHOLD,
        INTERACTIVE_QUEUE,
        app as celery_app,
    )

    # 仅传任务ID保持消息轻量, 参数由 worker 从库读取;
    # 物理队列路由(REQ-018 批次 2): 会话交互类(priority>=7, 如对话附件解析)走
    # q_interactive 独立队列, 批量任务积压不影响用户在等的交互任务; 其余走默认队列
    queue = (
        INTERACTIVE_QUEUE
        if (task.priority or 0) >= INTERACTIVE_PRIORITY_THRESHOLD
        else DEFAULT_QUEUE
    )
    async_result = celery_app.send_task(
        task_def.celery_task,
        args=[task.id],
        queue=queue,
        priority=task.priority,
    )
    return async_result.id


async def load_task(task_id: str) -> tuple[dict, str]:
    """
    worker 侧读取任务参数与创建者(任务消息只传ID保持轻量, 参数从库中读)
    :param task_id: task_queue 表主键
    :return: (payload参数dict, 创建者user_id)
    :raises ValueError: 任务不存在
    """
    from module_task.do.task import TaskQueue

    async with db_manager.db_rel.session_factory() as session:
        task = await session.get(TaskQueue, task_id)
        if task is None:
            raise ValueError(f"任务 {task_id} 不存在")
        return dict(task.payload or {}), task.user_id

# ################ worker 侧回写辅助 ################

async def update_task_fields(
    task_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    result: dict | None = None,
    error: str | None = None,
    set_started: bool = False,
    set_finished: bool = False,
) -> None:
    """
    worker 侧更新任务字段(独立短事务, 进度可频繁回写)

    终态保护采用条件 UPDATE(仅活跃态可写, 数据库端原子判定):
    修复"先读后写"竞态 —— 取消/cancel 与 runner 首次 RUNNING 回写并发时,
    后提交的事务不再覆盖已写入的终态(取消不会被回写复活)。
    :param task_id: 任务ID
    :param status: 目标状态(None 表示不更新)
    :param progress: 完成百分比 0~100
    :param message: 当前阶段描述
    :param result: 执行结果 JSON
    :param error: 失败原因
    :param set_started: 置 started_at 为当前时间(仅原值为空时, CASE 保持首次语义)
    :param set_finished: 置 finished_at 为当前时间(任务结束时)
    """
    from datetime import datetime, timezone

    from sqlalchemy import case, update

    from module_task.do.task import QueueTaskStatus, TaskQueue

    values: dict = {}
    if status is not None:
        values["status"] = status
    if progress is not None:
        values["progress"] = max(0.0, min(100.0, float(progress)))
    if message is not None:
        values["message"] = message
    if result is not None:
        values["result"] = result
    if error is not None:
        values["error"] = error
    now = datetime.now(timezone.utc)
    if set_started:
        values["started_at"] = case(
            (TaskQueue.started_at.is_(None), now), else_=TaskQueue.started_at
        )
    if set_finished:
        values["finished_at"] = now
    if not values:
        return

    async with db_manager.db_rel.session_factory() as session:
        async with session.begin():
            stmt = (
                update(TaskQueue)
                .where(
                    TaskQueue.id == task_id,
                    # 终态原子保护: 仅活跃态可写(取消/终态不被并发回写覆盖)
                    TaskQueue.status.in_((QueueTaskStatus.PENDING, QueueTaskStatus.RUNNING)),
                )
                .values(**values)
            )
            result = await session.execute(stmt)
    # REQ-011 终态埋点: 本次真实写入成功/失败终态(而非被终态保护跳过)时,
    # 后台通知任务创建者(取消/撤销不通知); 通知失败仅日志, 不影响任务回写
    if (
        result.rowcount
        and set_finished
        and status in (QueueTaskStatus.SUCCESS, QueueTaskStatus.FAILED)
    ):
        bg = asyncio.create_task(
            _notify_task_finished(task_id, status, error), name=f"notify:{task_id}"
        )
        _notify_tasks.add(bg)
        bg.add_done_callback(_notify_tasks.discard)


# 终态通知后台任务引用集(防 GC; 测试可等待其清空后再断言站内信落库)
_notify_tasks: set[asyncio.Task] = set()


async def _notify_task_finished(task_id: str, status: str, error: str | None) -> None:
    """任务终态通知(REQ-011 首个埋点接入): 读任务名与创建者 → 通知中心"""
    try:
        from module_task.do.task import TaskQueue

        async with db_manager.db_rel.session_factory() as session:
            task = await session.get(TaskQueue, task_id)
            if task is None or not task.user_id:
                return
            name, user_id = task.name, task.user_id
        from module_contact.service.notification import get_notification_service

        if status == QueueTaskStatus.SUCCESS:
            title = f"任务成功: {name}"
            content = f"后台任务「{name}」已成功完成。"
        else:
            title = f"任务失败: {name}"
            content = f"后台任务「{name}」执行失败: {(error or '未知原因')[:500]}"
        await get_notification_service().notify(user_id, "task_done", title, content)
    except Exception as exc:  # noqa: BLE001  # 通知属尽力而为, 失败不反噬任务链路
        logger.debug(f"任务终态通知失败(忽略): {exc}")

# ################ worker 启动自愈 ################

async def recover_pending_tasks(min_age_seconds: int = 60, stale_limit_days: int = 7) -> int:
    """
    兜底重派发: 扫描"长期 PENDING 且从未成功派发"的任务
    (celery_task_id 为空, 多为 派发瞬间崩溃 或 消息丢失), 重新投递 broker。
    消息只携带 task_id, 重复派发安全(消费侧按 ID 读库, 业务执行本身可重入)。

    超龄死任务保护: 创建超过 stale_limit_days 仍 PENDING 的任务直接置为失败终态
    (多为资源已删除的遗留任务, 如文档已删/向量模型已换), 反复重派发只会
    每次启动重复报错刷屏。

    由 app_task.py worker 启动时调用
    :param min_age_seconds: 仅处理创建超过该秒数的任务(避开与派发过程竞态)
    :param stale_limit_days: 超过该天数的 PENDING 任务视为死任务, 置失败不再重派发
    :return: 重派发的任务数
    """
    from datetime import datetime, timedelta, timezone

    from sqlmodel import select

    from module_task.do.task import QueueTaskStatus, TaskQueue

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_age_seconds)
    stale_deadline = datetime.now(timezone.utc) - timedelta(days=stale_limit_days)
    recovered = 0
    retired = 0
    async with db_manager.db_rel.session_factory() as session:
        rows = await session.exec(
            select(TaskQueue).where(
                TaskQueue.status == QueueTaskStatus.PENDING,
                TaskQueue.celery_task_id.is_(None),  # type: ignore[attr-defined]
                TaskQueue.created_at < cutoff,
            )
        )
        stale = list(rows.all())
        for task in stale:
            # 超龄死任务: 直接置失败终态(不再重派发, 避免启动刷屏)
            if task.created_at and task.created_at < stale_deadline:
                task.status = QueueTaskStatus.FAILED
                task.error = f"任务创建超过 {stale_limit_days} 天仍未执行成功, 已按死任务归档(资源可能已删除)"
                task.finished_at = datetime.now(timezone.utc)
                await session.commit()
                retired += 1
                continue
            task_def = get_task_type(task.task_type)
            if task_def is None:
                continue
            try:
                task.celery_task_id = await dispatch_task(task, task_def)
                await session.commit()
                recovered += 1
                # 逐条明细降为 debug(启动批量自愈时避免刷屏), 汇总数量见下方 info
                logger.debug(f"自愈重派发任务 {task.id}({task.task_type})")
            except Exception as exc:
                logger.warning(f"自愈重派发失败 {task.id}: {exc}")
                await session.rollback()
    if recovered:
        logger.info(f"任务队列自愈完成, 重派发 {recovered} 个遗留任务")
    if retired:
        logger.info(f"任务队列清理完成, 归档 {retired} 个超龄死任务(> {stale_limit_days} 天)")
    return recovered


async def fail_stale_running_tasks(stale_minutes: int = 30) -> int:
    """
    僵尸 RUNNING 清扫(worker 进程崩溃/OOM/重启遗留): started_at 超时且 Celery 侧
    无活跃心跳的任务 → 先按结果后端终态对账(SUCCESS/FAILURE/REVOKED), 仍无任何
    状态则置 FAILED 终态归档(否则会永久卡在 running)。

    误杀保护: 正常运行的任务会周期性 update_state(PROGRESS/STARTED/RETRY),
    活跃状态直接跳过 —— 长耗时任务只要还在回写进度就不会被清理。

    由 app_task.py 的 Reaper 线程周期调用(经 Redis 分布式锁保证全局单实例执行)。
    :param stale_minutes: started_at 超过该分钟数视为可疑
    :return: 清扫(含终态对账校正)的任务数
    """
    from datetime import datetime, timedelta, timezone

    from sqlmodel import select

    from module_task.do.task import QueueTaskStatus, TaskQueue

    deadline = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    swept = 0
    async with db_manager.db_rel.session_factory() as session:
        rows = await session.exec(
            select(TaskQueue).where(
                TaskQueue.status == QueueTaskStatus.RUNNING,
                TaskQueue.started_at.is_not(None),  # type: ignore[attr-defined]
                TaskQueue.started_at < deadline,
            )
        )
        for task in rows.all():
            celery_state = None
            if task.celery_task_id:
                try:
                    from common.config.tasks import app as celery_app

                    celery_state = celery_app.AsyncResult(task.celery_task_id).state
                except Exception:
                    celery_state = None  # 结果后端不可用: 按无心跳超时处理
            # 活跃心跳: 任务实际仍在运行, 跳过不误杀
            if celery_state in ("STARTED", "PROGRESS", "RETRY"):
                continue
            if celery_state == "SUCCESS":
                task.status = QueueTaskStatus.SUCCESS
                task.progress = 100
                task.message = "处理完成(由清扫对账恢复)"
            elif celery_state == "FAILURE":
                task.status = QueueTaskStatus.FAILED
                task.error = "任务失败(由清扫对账恢复)"
            elif celery_state == "REVOKED":
                task.status = QueueTaskStatus.REVOKED
                task.error = "已被撤销(由清扫对账恢复)"
            else:
                task.status = QueueTaskStatus.FAILED
                task.error = (
                    f"任务运行超过 {stale_minutes} 分钟无心跳, "
                    "疑似 worker 异常退出, 已由清扫归档"
                )
            task.finished_at = datetime.now(timezone.utc)
            await session.commit()
            swept += 1
            logger.warning(f"僵尸任务清扫: {task.id}({task.task_type}) -> {task.status}")
            # 兜底撤销 Celery 侧(僵尸若仍残留在某 worker 执行, 避免归档后双跑)
            if task.celery_task_id and celery_state != "SUCCESS":
                try:
                    from common.config.tasks import app as celery_app

                    celery_app.control.revoke(task.celery_task_id, terminate=True)
                except Exception:
                    pass  # 撤销失败不影响归档(终态保护已阻止僵尸回写复活)
    if swept:
        logger.info(f"任务队列清扫完成, 归档 {swept} 个僵尸 RUNNING 任务")
    return swept


async def init_worker_authorization() -> None:
    """
    worker 进程权限上下文初始化: 轻量构建 casbin enforcer 并从库加载策略。
    仅读不写(默认策略由 API 进程负责同步), 供任务执行时以创建者身份复检权限
    (is_global_admin / enforce_project_permission 均依赖该 enforcer)。
    """
    from module_authorization.config.casbin_rule import auth_manager

    await auth_manager.init_enforcer_only()
