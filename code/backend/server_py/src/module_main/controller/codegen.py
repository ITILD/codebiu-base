"""系统主模块 代码生成器接口层: 参数校验并调度 service

权限:
    - 读取类端点(表清单/表详情/字段建议/预览) -> sys:codegen:read
    - 生成写盘端点 -> sys:codegen:create
"""

from fastapi import APIRouter, Depends, Query

from common.config.server import app
from module_authorization.dependencies.permission import require_permission
from module_main.dependencies.codegen import get_codegen_service
from module_main.do.codegen import (
    GenerateRequest,
    GenerateResponse,
    PreviewRequest,
    PreviewResponse,
    SuggestRequest,
    SuggestResponse,
    TableDetail,
    TableListResponse,
)
from module_main.service.codegen import CodegenService

router = APIRouter()


@router.get("/tables", summary="列出可生成代码的数据表")
async def list_tables(
    keyword: str | None = Query(None, description="表名/注释关键字过滤"),
    service: CodegenService = Depends(get_codegen_service),
    _current_user_id: str = Depends(require_permission("sys", "codegen", "read")),
) -> TableListResponse:
    """
    读取 SQLModel 注册表中的全部表元数据

    :param keyword: 表名/注释关键字过滤
    :param service: 代码生成器服务
    :return: 表清单
    """
    return service.list_tables(keyword)


@router.get("/tables/{table_name}", summary="获取单表元数据")
async def get_table(
    table_name: str,
    service: CodegenService = Depends(get_codegen_service),
    _current_user_id: str = Depends(require_permission("sys", "codegen", "read")),
) -> TableDetail:
    """
    获取单表字段元数据(类型/可空/主键/默认值/注释/长度)

    :param table_name: 表名
    :param service: 代码生成器服务
    :return: 表详情
    """
    return service.get_table(table_name)


@router.post("/suggest", summary="生成字段配置建议(可选 AI 辅助)")
async def suggest(
    request: SuggestRequest,
    service: CodegenService = Depends(get_codegen_service),
    _current_user_id: str = Depends(require_permission("sys", "codegen", "read")),
) -> SuggestResponse:
    """
    根据表结构推断模块名/类名/页面标题与字段控件配置

    AI 不可用或返回非法 JSON 时自动回退启发式规则, 不会让请求失败。

    :param request: 建议请求
    :param service: 代码生成器服务
    :return: 命名/字段建议/提示
    """
    return await service.suggest(request)


@router.post("/preview", summary="预览生成代码")
async def preview(
    request: PreviewRequest,
    service: CodegenService = Depends(get_codegen_service),
    _current_user_id: str = Depends(require_permission("sys", "codegen", "read")),
) -> PreviewResponse:
    """
    渲染后端七层 + 前端模块代码并返回内容(不写盘)

    :param request: 预览请求
    :param service: 代码生成器服务
    :return: 文件内容/是否存在/提示
    """
    return service.preview(request)


@router.post("/generate", summary="生成代码并写盘")
async def generate(
    request: GenerateRequest,
    service: CodegenService = Depends(get_codegen_service),
    _current_user_id: str = Depends(require_permission("sys", "codegen", "create")),
) -> GenerateResponse:
    """
    渲染并写入后端/前端源码目录(拒绝目录穿越, 默认不覆盖已存在文件)

    :param request: 生成请求
    :param service: 代码生成器服务
    :return: 已写入/已跳过文件与提示
    """
    return service.generate(request)


app.include_router(router, prefix="/codegen", tags=["代码生成器"])
