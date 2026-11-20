"""
worker 宿主机运维服务层(P3: 多机 docker compose 动态启停)

架构: 每台 worker 宿主机跑一个轻量 agent 容器(挂本机 docker.sock, Bearer 认证),
主服务经 sys_worker_host 注册表路由到各 agent, 实现:
    - 聚合视图: 各主机 task_worker 容器实时状态(关联心跳 → 在途任务/IP)
    - 副本伸缩: 扩容直接克隆容器(无风险); 缩容走安全流程
    - 容器运维: 单容器 start/stop/restart

缩容安全流程(backlog + inflight 双指标 + 稳定窗口 + 优雅摘除):
    1. 前置判定: backlog(注册表启用队列 LLEN 之和) > 0 且未 force → 中止(有积压不该缩)
    2. 选定缩容目标: 优先最空闲(worker 在途任务最少), 同空闲度取最新启动的
    3. 稳定窗口(默认 600s, 可调): 周期采样 backlog, 上涨(新流量涌入) → 中止剩余缩容
    4. 逐个摘除: agent docker stop(SIGTERM=celery warm shutdown, 等在途任务完成,
       grace 超时强杀后消息由 acks_late+reject_on_worker_lost 重投) + remove
    5. 心跳注册表 90s 内可见目标 offline, 前端闭环确认

缩容为后台任务(可能阻塞 grace*数量时长), 返回 op_id 供轮询;
docker.sock 仅暴露在 worker 机 agent 内, 主服务不直连任何宿主 docker。
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_task.dao.task import TaskQueueDao
from module_task.do.task import (
    WorkerContainerInfo,
    WorkerHost,
    WorkerHostCreate,
    WorkerHostUpdate,
    WorkerHostView,
    WorkerScaleOpView,
)
from module_task.service.task import scan_worker_heartbeats, total_backlog

logger = logging.getLogger(__name__)

# agent 侧管理的 compose 服务名(约定与 docker-compose.yml 的 task_worker 服务一致)
WORKER_SERVICE = "task_worker"
# agent 默认地址端口(登记主机时未写全可推导)
_AGENT_TIMEOUT = 5.0        # 常规 agent 请求超时(秒)
_SAMPLE_INTERVAL = 15       # 缩容稳定窗口的 backlog 采样间隔(秒)
_DEFAULT_GRACE = 600        # docker stop 等待优雅退出的默认时长(秒) >= 最长任务时长
_MAX_OPS = 20               # 内存保留的最近伸缩操作数

# 伸缩操作登记(进程内存; 操作为幂等收敛型, API 重启丢失可接受)
_scale_ops: dict[str, dict] = {}


class WorkerHostService:
    def __init__(self, dao: TaskQueueDao):
        self.dao = dao

    # ################ 聚合视图 ################

    async def list_hosts(self) -> list[WorkerHostView]:
        """全部主机聚合视图(并发探测各 agent, 单机故障不影响整体)"""
        hosts = await self.dao.list_worker_hosts()
        if not hosts:
            return []
        heartbeats = scan_worker_heartbeats()  # hostname -> 心跳(轻量, 不走 inspect)
        hb_by_host: dict[str, dict] = {}
        for hb in heartbeats.values():
            hostname = hb.get("hostname")
            if hostname:
                hb_by_host[hostname] = hb
        views = await asyncio.gather(
            *(self._host_view(host, hb_by_host) for host in hosts)
        )
        return list(views)

    async def _host_view(self, host: WorkerHost, hb_by_host: dict[str, dict]) -> WorkerHostView:
        """单主机视图: agent 容器列表 + 心跳关联(容器 hostname ↔ worker 节点)"""
        view = WorkerHostView(
            id=host.id,
            host_name=host.host_name,
            agent_url=host.agent_url,
            description=host.description,
            enabled=host.enabled,
            has_token=bool(host.agent_token),
        )
        if not host.enabled:
            view.error = "主机已停用"
            return view
        try:
            containers = await _agent_request(
                host, "GET", "/containers", params={"service": WORKER_SERVICE}
            )
        except BusinessError as exc:
            view.error = str(exc)
            return view
        view.reachable = True
        for c in containers or []:
            hb = hb_by_host.get(c.get("hostname") or "")
            view.containers.append(
                WorkerContainerInfo(
                    id=c.get("id", ""),
                    name=c.get("name", ""),
                    hostname=c.get("hostname"),
                    state=c.get("state", "unknown"),
                    status=c.get("status", ""),
                    started_at=c.get("started_at"),
                    worker_name=hb.get("name") if hb else None,
                    worker_ip=hb.get("ip") if hb else None,
                    worker_active=int(hb.get("active", 0)) if hb else 0,
                    worker_queues=(hb.get("queues") or []) if hb else [],
                )
            )
        view.running = sum(1 for c in view.containers if c.state == "running")
        view.total = len(view.containers)
        return view

    # ################ 注册表 CRUD ################

    async def create_host(self, data: WorkerHostCreate) -> WorkerHostView:
        """登记 worker 宿主机(立即探活验证 agent 可达性)"""
        existing = await self.dao.list_worker_hosts()
        if any(h.host_name == data.host_name for h in existing):
            raise BusinessError(f"主机名 {data.host_name} 已登记")
        row = WorkerHost(
            host_name=data.host_name,
            agent_url=data.agent_url.rstrip("/"),
            agent_token=data.agent_token or None,
            description=data.description,
            enabled=data.enabled,
        )
        await self.dao.add_worker_host(row)
        return await self._host_view(row, {})

    async def update_host(self, host_id: str, data: WorkerHostUpdate) -> WorkerHostView:
        """更新主机登记(agent_token 传 null 清除)"""
        row = await self._get_or_404(host_id)
        if data.agent_url is not None:
            row.agent_url = data.agent_url.rstrip("/")
        if data.agent_token is not None:
            row.agent_token = data.agent_token or None
        if data.description is not None:
            row.description = data.description
        if data.enabled is not None:
            row.enabled = data.enabled
        await self.dao.update_worker_host(row)
        return await self._host_view(row, {})

    async def delete_host(self, host_id: str) -> None:
        """删除主机登记(不影响其上容器, 仅主服务不再纳管)"""
        await self.dao.delete_worker_host(host_id)

    # ################ 副本伸缩 ################

    async def scale(
        self,
        host_id: str,
        replicas: int,
        *,
        force: bool = False,
        stable_seconds: int = 600,
        grace: int = _DEFAULT_GRACE,
    ) -> WorkerScaleOpView:
        """
        伸缩主机 worker 副本到目标数

        - 扩容(目标 > 当前运行数): 直接克隆最新容器, 无风险, 同步完成
        - 缩容(目标 < 当前运行数): 后台任务执行安全流程(见模块注释), 返回 op_id 轮询
        - 相等: 幂等完成(顺带清理已退出的残留容器)
        :raises BusinessError: agent 不可达 / 无克隆模板(主机从未启动过 worker)
        """
        if replicas < 0:
            raise BusinessError("目标副本数必须 >= 0")
        host = await self._get_or_404(host_id)
        if not host.enabled:
            raise BusinessError(f"主机 {host.host_name} 已停用, 请先启用")
        containers = await _agent_request(
            host, "GET", "/containers", params={"service": WORKER_SERVICE}
        )
        running = [c for c in containers or [] if c.get("state") == "running"]
        op = _new_op(host, len(running), replicas)
        _put_op(op)

        if replicas > len(running):
            # ---- 扩容: 直接克隆最新容器(compose 标签保留, 后续 compose up 可纳管) ----
            op["phase"] = "scaling"
            try:
                created = await _agent_request(
                    host, "POST", "/scale-up",
                    json_body={"service": WORKER_SERVICE, "count": replicas - len(running)},
                    timeout=120.0,
                )
                op["phase"] = "done"
                op["message"] = f"扩容完成: 新增 {len(created.get('created') or [])} 个容器"
            except BusinessError as exc:
                op["phase"] = "failed"
                op["message"] = f"扩容失败: {exc}"
            _touch(op)
            return _op_view(op)

        if replicas == len(running):
            op["phase"] = "done"
            op["message"] = "副本数已为目标值, 无需调整"
            _touch(op)
            return _op_view(op)

        # ---- 缩容: 后台安全流程 ----
        op["phase"] = "checking"
        op["message"] = f"缩容启动: {len(running)} -> {replicas}(安全流程)"
        _touch(op)
        asyncio.create_task(
            _scale_down_flow(op, host, running, replicas, force, stable_seconds, grace)
        )
        return _op_view(op)

    async def scale_op(self, op_id: str) -> WorkerScaleOpView:
        """查询伸缩操作状态(前端轮询闭环)"""
        op = _scale_ops.get(op_id)
        if op is None:
            raise NotFoundError(f"伸缩操作 {op_id} 不存在(可能服务已重启, 可刷新主机列表确认结果)")
        return _op_view(op)

    # ################ 容器运维 ################

    async def container_action(
        self, host_id: str, container_id: str, action: str, grace: int = 60
    ) -> dict:
        """
        单容器运维操作(start/stop/restart)
        :param grace: stop/restart 的优雅等待时长(秒), 长任务在途时建议调大
        """
        if action not in ("start", "stop", "restart"):
            raise BusinessError("不支持的操作, 仅允许 start/stop/restart")
        host = await self._get_or_404(host_id)
        if not host.enabled:
            raise BusinessError(f"主机 {host.host_name} 已停用")
        timeout = (grace + 60) if action != "start" else 60.0
        return await _agent_request(
            host, "POST", f"/containers/{container_id}/{action}",
            json_body={"grace": grace}, timeout=timeout,
        )

    async def drain_worker(self, worker_name: str) -> int:
        """
        优雅摘除指定 worker 节点: 广播 control.shutdown(停止取新任务, 在途任务完成后退出)

        注意: 容器化部署时进程退出会因 restart 策略自动拉起(等效滚动重启);
        永久下线请用主机缩容(docker stop 不受 restart 策略影响)。
        :return: 确认收到指令的 worker 数
        """

        def _shutdown() -> dict:
            from common.config.tasks import app as celery_app

            return celery_app.control.shutdown(
                destination=[worker_name], timeout=2.0, reply=True
            ) or {}

        try:
            replies = await asyncio.to_thread(_shutdown)
            return len(replies)
        except Exception as exc:
            raise BusinessError(f"下发 drain 指令失败: {exc}") from exc

    # ################ 内部 ################

    async def _get_or_404(self, host_id: str) -> WorkerHost:
        row = await self.dao.get_worker_host(host_id)
        if row is None:
            raise NotFoundError(f"未找到ID为 {host_id} 的宿主机")
        return row


# ################ agent HTTP 客户端 ################


async def _agent_request(
    host: WorkerHost, method: str, path: str, *,
    json_body: dict | None = None, params: dict | None = None,
    timeout: float = _AGENT_TIMEOUT,
) -> dict | list:
    """调用宿主机 agent(Bearer 认证; 401/403 → token 不一致, 连接失败 → agent 未启动)"""
    headers = {}
    if host.agent_token:
        headers["Authorization"] = f"Bearer {host.agent_token}"
    url = f"{host.agent_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method, url, headers=headers, json=json_body, params=params,
                timeout=timeout,
            )
    except httpx.HTTPError as exc:
        raise BusinessError(f"agent 不可达({url}): {exc.__class__.__name__}") from exc
    if resp.status_code in (401, 403):
        raise BusinessError("agent 认证失败: 主服务登记的 token 与 agent AGENT_TOKEN 不一致")
    if resp.status_code == 404:
        raise BusinessError("agent 接口不存在(请确认 agent 版本)")
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = str(resp.json().get("detail", ""))
        except Exception:
            pass
        raise BusinessError(f"agent 返回 {resp.status_code}: {detail or resp.text[:200]}")
    return resp.json()


# ################ 缩容后台流程 ################


async def _scale_down_flow(
    op: dict, host: WorkerHost, running: list[dict], replicas: int,
    force: bool, stable_seconds: int, grace: int,
) -> None:
    """缩容安全流程(后台任务): 积压判定 → 稳定窗口 → 逐容器优雅摘除"""
    try:
        from module_task.tasks import enabled_registry_queues

        queues = await enabled_registry_queues() or {"task_queue", "q_interactive"}
        # ---- 1. 前置判定: 有积压时缩容会拉长消化时间(除非 force) ----
        backlog = total_backlog(sorted(queues))
        op["phase"] = "checking"
        if not force and backlog and backlog > 0:
            op["phase"] = "aborted"
            op["message"] = f"中止缩容: 当前积压 {backlog} 条任务(确认无积压或 force 后重试)"
            _touch(op)
            return
        initial_backlog = backlog or 0

        # ---- 2. 选定缩容目标: 优先最空闲(在途任务最少), 同空闲度取最新启动 ----
        heartbeats = scan_worker_heartbeats()
        hb_by_host = {hb.get("hostname"): hb for hb in heartbeats.values() if hb.get("hostname")}

        def _busy(container: dict) -> tuple[int, str]:
            hb = hb_by_host.get(container.get("hostname") or "")
            active = int(hb.get("active", 0)) if hb else 0
            return active, container.get("started_at") or ""

        victims = sorted(running, key=_busy)[: len(running) - replicas]

        # ---- 3. 稳定窗口: 周期采样积压, 上涨(新流量涌入) → 中止 ----
        if stable_seconds > 0:
            op["phase"] = "waiting_stable"
            elapsed = 0
            while elapsed < stable_seconds:
                await asyncio.sleep(min(_SAMPLE_INTERVAL, stable_seconds - elapsed))
                elapsed += _SAMPLE_INTERVAL
                sample = total_backlog(sorted(queues))
                op["message"] = (
                    f"稳定窗口观察中 {elapsed}/{stable_seconds}s, 积压 {sample if sample is not None else '未知'} 条"
                )
                _touch(op)
                if not force and sample is not None and sample > initial_backlog:
                    op["phase"] = "aborted"
                    op["message"] = (
                        f"中止缩容: 积压由 {initial_backlog} 上涨至 {sample}(新流量涌入, 稍后重试)"
                    )
                    _touch(op)
                    return

        # ---- 4. 逐容器优雅摘除: docker stop(SIGTERM=celery warm shutdown 等在途完成) + remove ----
        op["phase"] = "draining"
        removed = 0
        for victim in victims:
            op["message"] = (
                f"正在摘除 {victim.get('name')}({removed + 1}/{len(victims)}, "
                f"在途 {hb_by_host.get(victim.get('hostname') or '', {}).get('active', 0)} 个任务)"
            )
            _touch(op)
            try:
                await _agent_request(
                    host, "POST", f"/containers/{victim['id']}/stop",
                    json_body={"grace": grace, "remove": True},
                    timeout=grace + 120.0,
                )
                removed += 1
            except BusinessError as exc:
                op["phase"] = "failed"
                op["message"] = f"摘除 {victim.get('name')} 失败(已摘除 {removed} 个): {exc}"
                _touch(op)
                return
        op["phase"] = "done"
        op["message"] = f"缩容完成: 摘除 {removed} 个容器, 剩余 {replicas} 副本(心跳 90s 内刷新)"
        _touch(op)
    except Exception as exc:  # 流程级兜底: 操作必须落一个终态
        op["phase"] = "failed"
        op["message"] = f"缩容流程异常: {exc}"
        _touch(op)
        logger.warning(f"缩容后台流程异常 host={host.host_name}: {exc}")


# ################ 操作登记辅助 ################


def _new_op(host: WorkerHost, from_count: int, to_count: int) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "op_id": uuid4().hex[:12],
        "host_id": host.id,
        "host_name": host.host_name,
        "from_count": from_count,
        "to_count": to_count,
        "phase": "checking",
        "message": None,
        "created_at": now,
        "updated_at": now,
    }


def _put_op(op: dict) -> None:
    """登记操作(保留最近 _MAX_OPS 条)"""
    if len(_scale_ops) >= _MAX_OPS:
        for key in sorted(_scale_ops, key=lambda k: _scale_ops[k]["updated_at"])[:-_MAX_OPS + 1]:
            _scale_ops.pop(key, None)
    _scale_ops[op["op_id"]] = op


def _touch(op: dict) -> None:
    op["updated_at"] = datetime.now(timezone.utc).isoformat()


def _op_view(op: dict) -> WorkerScaleOpView:
    return WorkerScaleOpView(**op)
