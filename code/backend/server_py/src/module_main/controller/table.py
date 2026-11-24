"""系统主模块 数据库表管理接口(建表/重置)"""


from common.config.server import app
from module_main.service.table import TableService
from module_main.service.db_meta import DbMetaService

# lib
from fastapi import APIRouter, Depends, status
from module_authorization.dependencies.auth import get_current_user_id
from module_authorization.dependencies.permission import require_permission
from module_authorization.config.casbin_rule import is_global_admin
from common.utils.fastapi_ex.exceptions import ForbiddenError
import logging
logger = logging.getLogger(__name__)
# 基础db
router = APIRouter()


async def require_global_admin(
    current_user_id: str = Depends(get_current_user_id),
) -> str:
    """依赖: 破坏性库操作(建表/重置)仅全局管理员可用"""
    if not is_global_admin(current_user_id):
        raise ForbiddenError("仅系统管理员可执行数据库结构操作")
    return current_user_id


# 测试
@router.get(
    "/create", summary="创建表", status_code=status.HTTP_201_CREATED
)
async def create(_: str = Depends(require_global_admin)):
    """
    创建所有未创建的数据库表(仅系统管理员)

    返回:
        HTTPException: 成功返回200状态码，失败返回500状态码
    """
    result = await TableService.create()
    return result


# 更新数据库
@router.get("/reset", summary="重置表", status_code=status.HTTP_201_CREATED)
async def reset(_: str = Depends(require_global_admin)):
    """
    更新所有数据库表(仅系统管理员; 会清空重建全部表, 破坏性操作)

    返回:
        HTTPException: 成功返回200状态码，失败返回500状态码
    """
    result = await TableService.reset()
    return result


# 数据表清单(只读)
@router.get("/tables", summary="数据表清单")
async def tables(
    keyword: str | None = None,
    _: str = Depends(require_permission("main", "db", "read")),
):
    """
    列出关系库数据表及数据量/最近更新时间

    Args:
        keyword: 按表名/注释关键字过滤

    Returns:
        list[dict]: name/comment/column_count/row_count/last_updated
    """
    return await DbMetaService.tables(keyword)


# 向量库表清单(只读)
@router.get("/vector", summary="向量库表清单")
async def vector_tables(
    _: str = Depends(require_permission("main", "db", "read")),
):
    """
    列出向量库表及字段数/向量维度/数据条数

    Returns:
        dict: {type, tables}
    """
    return await DbMetaService.vector_tables()


# 缓存数据库信息(只读)
@router.get("/cache", summary="缓存数据库信息")
async def cache_info(
    _: str = Depends(require_permission("main", "db", "read")),
):
    """
    Redis 缓存运行信息(键数量/内存/命中率/版本等)

    Returns:
        dict: 缓存概要信息
    """
    return await DbMetaService.cache_info()


# 图数据库信息(只读)
@router.get("/graph", summary="图数据库信息")
async def graph_info(
    _: str = Depends(require_permission("main", "db", "read")),
):
    """
    图数据库运行信息(未启用时 type 为 None)

    Returns:
        dict: 图库实现类型及自述信息
    """
    return await DbMetaService.graph_info()


app.include_router(router, prefix="/db", tags=["db"])
logger.debug("ok...controller_index")
