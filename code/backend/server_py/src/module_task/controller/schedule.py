"""任务队列模块 周期调度接口层(REQ-012): 参数校验并调度 service"""

from fastapi import APIRouter, Depends, Query, status

from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_authorization.dependencies.permission import require_permission
from module_task.config.server import module_app
from module_task.dependencies.schedule import get_task_schedule_service
from module_task.do.schedule import (
    CRON_PRESET_LIST,
    TaskScheduleCreate,
    TaskScheduleResponse,
    TaskScheduleTriggerResult,
    TaskScheduleUpdate,
)
from module_task.service.schedule import TaskScheduleService

router = APIRouter()


@router.get("/presets", summary="cron 快捷表达式预置", response_model=list)
async def get_cron_presets(
    current_user_id: str = Depends(require_permission("task", "schedule", "read")),
) -> list:
    """常用 cron 快捷选项(前端创建对话框渲染)"""
    return CRON_PRESET_LIST


@router.get("/list", summary="分页查询调度列表", response_model=PaginationResponse)
async def list_schedules(
    pagination: PaginationParams = Depends(),
    keyword: str | None = Query(None, max_length=200, description="调度名称模糊搜索"),
    enabled: bool | None = Query(None, description="启停过滤"),
    task_type: str | None = Query(None, description="任务类型过滤"),
    current_user_id: str = Depends(require_permission("task", "schedule", "read")),
    service: TaskScheduleService = Depends(get_task_schedule_service),
) -> PaginationResponse:
    """分页查询定时任务调度定义(含下次触发与最近执行快照)"""
    return await service.list_page(
        pagination, keyword=keyword, enabled=enabled, task_type=task_type
    )


@router.post("", summary="创建调度", status_code=status.HTTP_201_CREATED, response_model=TaskScheduleResponse)
async def create_schedule(
    data: TaskScheduleCreate,
    current_user_id: str = Depends(require_permission("task", "schedule", "create")),
    service: TaskScheduleService = Depends(get_task_schedule_service),
) -> TaskScheduleResponse:
    """
    创建周期调度(cron/间隔二选一; 创建即热生效)
    :raises BusinessError: 类型未注册/触发方式冲突/cron 非法(400)
    """
    return await service.create(data, current_user_id)


@router.put("/{schedule_id}", summary="修改调度(热生效)", response_model=TaskScheduleResponse)
async def update_schedule(
    schedule_id: int,
    data: TaskScheduleUpdate,
    current_user_id: str = Depends(require_permission("task", "schedule", "update")),
    service: TaskScheduleService = Depends(get_task_schedule_service),
) -> TaskScheduleResponse:
    """
    修改调度定义(启停/改周期即时热生效, local 循环立即唤醒)
    :raises NotFoundError: 调度不存在(404); BusinessError: 校验失败(400)
    """
    return await service.update(schedule_id, data)


@router.delete("/{schedule_id}", summary="删除调度", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: int,
    current_user_id: str = Depends(require_permission("task", "schedule", "delete")),
    service: TaskScheduleService = Depends(get_task_schedule_service),
) -> None:
    """删除调度定义(已派发任务不受影响)"""
    # 不存在 → 404(dao 层 NotFoundError 直接映射)
    await service.delete(schedule_id)


@router.post("/{schedule_id}/trigger", summary="立即触发一次", response_model=TaskScheduleTriggerResult)
async def trigger_schedule(
    schedule_id: int,
    current_user_id: str = Depends(require_permission("task", "schedule", "update")),
    service: TaskScheduleService = Depends(get_task_schedule_service),
) -> TaskScheduleTriggerResult:
    """
    手动立即触发一次(不影响周期节奏, 用于验证任务定义)
    :raises NotFoundError: 调度不存在(404)
    """
    return await service.trigger_now(schedule_id)


module_app.include_router(router, prefix="/schedules", tags=["定时任务"])
