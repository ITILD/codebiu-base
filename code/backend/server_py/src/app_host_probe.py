"""
worker 宿主机运维探针(REQ-019 §6.3: 部署形态, 与 app_task.py worker 同级的同镜像第二入口)

定位: 每台部署了 task_worker 的宿主机跑一个本探针容器(挂 /var/run/docker.sock),
主服务经 sys_worker_host 注册表路由 HTTP 调用本探针;
docker.sock 只暴露在本机探针内, 主服务不直连任何宿主 docker。

⚠️ 三层归位(REQ-019 §6.2): 本文件只是「探针入口」, 不再是运维逻辑的家 ——
   容器原语的唯一契约由 Skill 层 sys.container_*(module_task/skills/container_ops.py)
   定义, 伸缩/自愈编排由 ops_agent(sys.ops_worker_heal)承担, 全部调用可追溯
   (skill_invocation / agent_job_run); 本文件保持最小原语集不变以免部署脚本失效。

独立轻量服务(不加载项目 runtime/DB, 与业务代码零耦合):
    - 认证: 全部操作接口要求 Authorization: Bearer $AGENT_TOKEN
      (未设置 AGENT_TOKEN 时拒绝一切操作, 防止裸奔)
    - 最小攻击面: 仅容器 查看/启停/重启/克隆 四类原语, 按约定服务名过滤

用法(与主服务同一镜像, compose 里 host_probe 服务):
    AGENT_PORT=8700 AGENT_TOKEN=xxx python src/app_host_probe.py

接口:
    GET  /health                          探活(免认证, 不泄露信息)
    GET  /containers?service=task_worker  容器列表(全部状态, 含 hostname 供心跳关联)
    POST /scale-up                        克隆最新容器扩容 {service, count}
    POST /containers/{id}/start           启动已停止的容器
    POST /containers/{id}/stop            优雅停止 {grace, remove}
    POST /containers/{id}/restart         重启 {grace}
    POST /containers/{id}/remove          移除容器 {force}

说明:
    - stop = docker stop(SIGTERM): celery 收到后 warm shutdown(停止取新任务,
      等在途任务完成后退出), 超时 grace 秒强杀; acks_late + reject_on_worker_lost
      保证被强杀任务的消息重投其他 worker —— 优雅摘除与缩容安全的基石
    - docker stop 属"人工停止": unless-stopped 重启策略不会再拉起(与进程退出的
      自动重启区分), 因此缩容用 stop+remove, 滚动重启用 restart
    - 扩容克隆 = 复制最新容器的完整配置(compose 标签顺延编号, hostname=容器名),
      后续 docker compose up 仍可纳管这些容器
"""
import logging
import os
import socket

import docker
import uvicorn
from docker.errors import APIError, NotFound
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("host-probe")

AGENT_PORT = int(os.environ.get("AGENT_PORT", "8700"))
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
DOCKER_HOST_URL = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")

app = FastAPI(title="task-host-probe", docs_url=None, redoc_url=None)
_client: docker.DockerClient | None = None


def docker_client() -> docker.DockerClient:
    """docker SDK 客户端(惰性创建, 挂本机 docker.sock)"""
    global _client
    if _client is None:
        _client = docker.DockerClient(base_url=DOCKER_HOST_URL)
    return _client


def require_token(authorization: str | None) -> None:
    """Bearer 认证: token 未配置 → 拒绝一切操作; 不匹配 → 403"""
    if not AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="agent 未配置 AGENT_TOKEN, 拒绝操作")
    expected = f"Bearer {AGENT_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="token 校验失败")


def _container_summary(container) -> dict:
    """容器摘要(前端/心跳关联所需字段)"""
    attrs = container.attrs or {}
    name = (attrs.get("Name") or "").lstrip("/")
    return {
        "id": container.short_id,
        "name": name,
        "hostname": (attrs.get("Config") or {}).get("Hostname") or name,
        "state": attrs.get("State", {}).get("Status", "unknown"),
        "status": container.status,
        "started_at": attrs.get("State", {}).get("StartedAt") or None,
        "created_at": attrs.get("Created") or "",
    }


def _list_containers(service: str, state: str | None = None) -> list:
    """按 compose 服务标签过滤容器(全部状态; state 可再过滤 running/exited)"""
    filters = {"label": f"com.docker.compose.service={service}"}
    containers = docker_client().containers.list(all=True, filters=filters)
    if state:
        containers = [c for c in containers if (c.attrs or {}).get("State", {}).get("Status") == state]
    return containers


def _next_compose_number(containers: list, service: str) -> int:
    """解析现有容器编号(com.docker.compose.container-number)取最大值 +1"""
    numbers = []
    for c in containers:
        raw = ((c.attrs or {}).get("Config") or {}).get("Labels") or {}
        try:
            numbers.append(int(raw.get("com.docker.compose.container-number", "1")))
        except (TypeError, ValueError):
            continue
    return max(numbers, default=0) + 1


def _clone_container(service: str, template, name: str) -> str:
    """
    克隆容器: 以模板容器的完整 inspect 配置创建同名新容器并启动

    - compose 标签全部保留并顺延编号 → docker compose up 仍可纳管
    - hostname=新容器名 → worker 心跳注册的 hostname 与容器一一对应
    - 环境/挂载/网络/重启策略 原样复制(与模板同角色同配置)
    """
    api = docker_client().api
    info = api.inspect_container(template.id)
    cfg = info["Config"]
    labels = dict(cfg.get("Labels") or {})
    number = str(_next_compose_number(_list_containers(service), service))
    labels["com.docker.compose.container-number"] = number
    labels.pop("com.docker.compose.config-hash", None)  # 让 compose 后续 up 重建校验
    networks = info["NetworkSettings"]["Networks"]
    created = api.create_container(
        name=name,
        image=cfg["Image"],
        command=cfg.get("Cmd"),
        entrypoint=cfg.get("Entrypoint"),
        environment=cfg.get("Env"),
        labels=labels,
        host_config=info["HostConfig"],
        networking_config={"EndpointsConfig": networks},
        working_dir=cfg.get("WorkingDir"),
        user=cfg.get("User"),
        tty=bool(cfg.get("Tty")),
        stdin_open=bool(cfg.get("OpenStdin")),
        hostname=name,
    )
    api.start(created["Id"])
    return name


@app.get("/health")
def health() -> dict:
    """探活(免认证, 不泄露任何配置)"""
    try:
        version = docker_client().version()["Version"]
    except Exception:
        version = "unreachable"
    return {"ok": True, "host": socket.gethostname(), "docker": version}


@app.get("/containers")
def list_containers(
    service: str,
    authorization: str | None = Header(default=None),
) -> list[dict]:
    """指定 compose 服务的容器列表(全部状态)"""
    require_token(authorization)
    try:
        return [_container_summary(c) for c in _list_containers(service)]
    except APIError as exc:
        raise HTTPException(status_code=500, detail=f"docker 接口异常: {exc}") from exc


class ScaleUpBody(BaseModel):
    service: str = Field(description="compose 服务名")
    count: int = Field(default=1, ge=1, description="新增容器数")


@app.post("/scale-up")
def scale_up(body: ScaleUpBody, authorization: str | None = Header(default=None)) -> dict:
    """
    克隆扩容: 以最新运行中容器(无则最新任意状态容器)为模板克隆 count 份
    容器命名遵循 compose 规约 <project>-<service>-<number>
    """
    require_token(authorization)
    containers = _list_containers(body.service)
    if not containers:
        raise HTTPException(status_code=400, detail=f"无 {body.service} 容器可作克隆模板, 请先用 compose 启动")
    running = [c for c in containers if c.attrs.get("State", {}).get("Status") == "running"]
    template = sorted(
        running or containers,
        key=lambda c: (c.attrs or {}).get("Created") or "",
    )[-1]
    labels = ((template.attrs or {}).get("Config") or {}).get("Labels") or {}
    project = labels.get("com.docker.compose.project") or "codebiu"
    try:
        created = []
        for _ in range(body.count):
            number = _next_compose_number(_list_containers(body.service), body.service)
            name = f"{project}-{body.service}-{number}"
            _clone_container(body.service, template, name)
            created.append(name)
        return {"created": created}
    except APIError as exc:
        raise HTTPException(status_code=500, detail=f"克隆容器失败: {exc}") from exc


class StopBody(BaseModel):
    grace: int = Field(default=600, ge=1, le=3600, description="优雅等待(秒), 建议>=最长任务时长")
    remove: bool = Field(default=False, description="停止后是否移除容器(缩容用)")


def _get_container(container_id: str):
    """按短 ID 定位容器(兼容完整 ID)"""
    try:
        return docker_client().containers.get(container_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=f"容器 {container_id} 不存在") from exc


@app.post("/containers/{container_id}/stop")
def stop_container(container_id: str, body: StopBody,
                   authorization: str | None = Header(default=None)) -> dict:
    """优雅停止(SIGTERM=warm shutdown 等 在途任务, 超时强杀后消息重投), 可选移除"""
    require_token(authorization)
    container = _get_container(container_id)
    try:
        container.stop(timeout=body.grace)
        if body.remove:
            container.remove()
        return {"id": container_id, "state": "removed" if body.remove else "exited"}
    except APIError as exc:
        raise HTTPException(status_code=500, detail=f"停止容器失败: {exc}") from exc


@app.post("/containers/{container_id}/start")
def start_container(container_id: str, authorization: str | None = Header(default=None)) -> dict:
    """启动已停止的容器"""
    require_token(authorization)
    container = _get_container(container_id)
    try:
        container.start()
        return {"id": container_id, "state": "running"}
    except APIError as exc:
        raise HTTPException(status_code=500, detail=f"启动容器失败: {exc}") from exc


@app.post("/containers/{container_id}/restart")
def restart_container(container_id: str, body: StopBody,
                      authorization: str | None = Header(default=None)) -> dict:
    """重启容器(grace 秒内等优雅退出, 超时强杀)"""
    require_token(authorization)
    container = _get_container(container_id)
    try:
        container.restart(timeout=body.grace)
        return {"id": container_id, "state": "running"}
    except APIError as exc:
        raise HTTPException(status_code=500, detail=f"重启容器失败: {exc}") from exc


class RemoveBody(BaseModel):
    force: bool = Field(default=False, description="运行中也强制移除(先 stop)")


@app.post("/containers/{container_id}/remove")
def remove_container(container_id: str, body: RemoveBody,
                     authorization: str | None = Header(default=None)) -> dict:
    """移除容器(force 时先停止)"""
    require_token(authorization)
    container = _get_container(container_id)
    try:
        container.remove(force=body.force)
        return {"id": container_id, "state": "removed"}
    except APIError as exc:
        raise HTTPException(status_code=500, detail=f"移除容器失败: {exc}") from exc


if __name__ == "__main__":
    if not AGENT_TOKEN:
        logger.warning("AGENT_TOKEN 未设置: agent 将拒绝所有操作接口(仅 /health 可用)")
    logger.info(f"host probe 启动: port={AGENT_PORT} docker={DOCKER_HOST_URL}")
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
