"""系统主模块 操作审计日志接口层(REQ-009): 管理端条件查询"""

from datetime import datetime

from fastapi import APIRouter, Depends

from common.config.server import app
from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_authorization.dependencies.permission import require_permission
from module_main.dependencies.audit_log import get_audit_log_service
from module_main.service.audit_log import AuditLogService

router = APIRouter()


@router.get("/list", summary="分页查询操作审计日志", response_model=PaginationResponse)
async def list_audit_logs(
    pagination: PaginationParams = Depends(),
    service: AuditLogService = Depends(get_audit_log_service),
    current_user_id: str = Depends(require_permission("sys", "audit", "read")),
    user_id: str | None = None,
    username: str | None = None,
    method: str | None = None,
    keyword: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> PaginationResponse:
    """
    按用户/方法/路径关键字/时间段过滤分页查询(记录时间倒序)
    权限: sys:audit:read(仅管理员角色默认授予)
    """
    return await service.list_paged(
        pagination,
        user_id=user_id,
        username=username,
        method=method,
        keyword=keyword,
        start=start,
        end=end,
    )


app.include_router(router, prefix="/audit_logs", tags=["操作审计"])
