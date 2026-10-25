"""系统主模块 多语言词条覆盖接口层

权限:
    - GET /overrides、/export 仅登录校验(应用启动时普通用户也要能拉取词条热更新)
    - PUT/POST/DELETE 需要 sys:i18n:edit(默认仅管理员)
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from common.config.server import app
from module_authorization.dependencies.auth import get_current_user_id
from module_authorization.dependencies.permission import require_permission
from module_main.dependencies.i18n import get_i18n_service
from module_main.do.i18n import (
    I18nCountResponse,
    I18nExportResponse,
    I18nImportRequest,
    I18nImportResponse,
    I18nOverrideBulkPut,
    I18nOverrideResponse,
)
from module_main.service.i18n import I18nService

router = APIRouter()


@router.get("/overrides", summary="查询全部词条覆盖", response_model=list[I18nOverrideResponse])
async def list_overrides(
    current_user_id: str = Depends(get_current_user_id),
    service: I18nService = Depends(get_i18n_service),
) -> list[I18nOverrideResponse]:
    """全量词条覆盖(按 key 升序; 登录即可, 供前端启动时热更新)"""
    return await service.list_all()


@router.put("/overrides", summary="批量写入词条覆盖", response_model=I18nCountResponse)
async def bulk_put_overrides(
    data: I18nOverrideBulkPut,
    current_user_id: str = Depends(require_permission("sys", "i18n", "edit")),
    service: I18nService = Depends(get_i18n_service),
) -> I18nCountResponse:
    """
    批量 upsert 词条覆盖(单事务)
    :raises BusinessError: 存在空 key(400)
    """
    return await service.bulk_put(data)


@router.delete(
    "/overrides/{key:path}",
    summary="删除词条覆盖",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_override(
    key: str,
    current_user_id: str = Depends(require_permission("sys", "i18n", "edit")),
    service: I18nService = Depends(get_i18n_service),
) -> Response:
    """按 key 删除词条覆盖(不存在也返回 204, 幂等)"""
    await service.delete(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export", summary="导出词条覆盖", response_model=I18nExportResponse)
async def export_overrides(
    current_user_id: str = Depends(get_current_user_id),
    service: I18nService = Depends(get_i18n_service),
) -> I18nExportResponse:
    """导出全部词条覆盖(key/zh/ja/en, 不含时间戳; 登录即可)"""
    return await service.export()


@router.post("/import", summary="导入词条覆盖", response_model=I18nImportResponse)
async def import_overrides(
    data: I18nImportRequest,
    current_user_id: str = Depends(require_permission("sys", "i18n", "edit")),
    service: I18nService = Depends(get_i18n_service),
) -> I18nImportResponse:
    """
    导入词条覆盖(单事务); overwrite=False 时已存在 key 跳过并返回 skipped
    :raises BusinessError: 存在空 key(400)
    """
    return await service.import_items(data)


app.include_router(router, prefix="/i18n", tags=["多语言词条"])
