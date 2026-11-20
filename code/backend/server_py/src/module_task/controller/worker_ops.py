"""worker 宿主机运维接口层(P3): 主机纳管/副本伸缩/容器运维/优雅摘除

全部接口要求执行器运维权限(task:worker:manage), 操作经既有审计中间件留痕。
"""

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, status

from module_authorization.dependencies.permission import require_permission
from module_task.config.server import module_app
from module_task.dependencies.task import get_worker_host_service
from module_task.do.task import (
    WorkerHostCreate,
    WorkerHostUpdate,
    WorkerHostView,
    WorkerScaleOpView,
)
from module_task.service.worker_host import WorkerHostService

router = APIRouter()


@router.get("/hosts", summary="查询worker宿主机聚合状态", response_model=list[WorkerHostView])
async def list_hosts(
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> list[WorkerHostView]:
    """全部主机视图: agent 可达性 + task_worker 容器列表(关联 worker 心跳)"""
    return await service.list_hosts()


@router.post("/hosts", summary="登记worker宿主机", status_code=status.HTTP_201_CREATED,
             response_model=WorkerHostView)
async def create_host(
    data: WorkerHostCreate,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> WorkerHostView:
    """登记宿主机(agent 地址 + Bearer token, 立即探活验证)"""
    return await service.create_host(data)


@router.patch("/hosts/{host_id}", summary="更新worker宿主机登记", response_model=WorkerHostView)
async def update_host(
    host_id: str,
    data: WorkerHostUpdate,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> WorkerHostView:
    """更新主机登记(agent_url/token/启停/说明)"""
    return await service.update_host(host_id, data)


@router.delete("/hosts/{host_id}", summary="删除worker宿主机登记",
               status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: str,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> None:
    """删除主机登记(不影响其上容器, 仅主服务不再纳管)"""
    await service.delete_host(host_id)


class WorkerScaleBody(BaseModel):
    """副本伸缩请求体"""

    replicas: int = Field(ge=0, description="目标副本数")
    force: bool = Field(default=False, description="跳过积压判定与稳定窗口(紧急缩容)")
    stable_seconds: int = Field(
        default=600, ge=0,
        description="缩容稳定窗口(秒): 观察积压无上涨才执行; 0=跳过",
    )
    grace: int = Field(
        default=600, ge=1, le=3600,
        description="docker stop 优雅等待(秒), 建议 >= 最长任务时长",
    )


@router.post("/hosts/{host_id}/scale", summary="伸缩worker副本数", response_model=WorkerScaleOpView)
async def scale_host(
    host_id: str,
    body: WorkerScaleBody,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> WorkerScaleOpView:
    """
    伸缩副本数: 扩容直接克隆容器(同步完成);
    缩容走安全流程(积压判定 → 稳定窗口 → 逐容器优雅摘除), 后台执行, 轮询 op 状态
    """
    return await service.scale(
        host_id, body.replicas,
        force=body.force, stable_seconds=body.stable_seconds, grace=body.grace,
    )


@router.get("/scale-ops/{op_id}", summary="查询伸缩操作状态", response_model=WorkerScaleOpView)
async def get_scale_op(
    op_id: str,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> WorkerScaleOpView:
    """伸缩操作状态(phase: checking/waiting_stable/draining/scaling/done/failed/aborted)"""
    return await service.scale_op(op_id)


class ContainerActionBody(BaseModel):
    """容器运维请求体"""

    grace: int = Field(default=60, ge=1, le=3600, description="stop/restart 优雅等待(秒)")


@router.post("/hosts/{host_id}/containers/{container_id}/{action}",
             summary="容器运维(start/stop/restart)")
async def container_action(
    host_id: str,
    container_id: str,
    action: str,
    body: ContainerActionBody | None = None,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> dict:
    """单容器运维: start/stop/restart(stop 等在途任务完成后退出, 不删除容器)"""
    grace = body.grace if body else 60
    return await service.container_action(host_id, container_id, action, grace)


@router.post("/drain/{worker_name}", summary="优雅摘除worker节点", response_model=int)
async def drain_worker(
    worker_name: str,
    current_user_id: str = Depends(require_permission("task", "worker", "manage")),
    service: WorkerHostService = Depends(get_worker_host_service),
) -> int:
    """
    广播 control.shutdown: 目标 worker 停止取新任务, 在途任务完成后退出
    (容器化部署因 restart 策略会自动拉起, 等效滚动重启; 永久下线请用主机缩容)
    """
    return await service.drain_worker(worker_name)


module_app.include_router(router, prefix="/workers", tags=["执行器运维"])
