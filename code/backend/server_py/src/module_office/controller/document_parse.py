"""
文件解析成markdown
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response

from module_authorization.dependencies.auth import get_current_user_id
from module_authorization.dependencies.permission import require_permission
from module_office.config.server import module_app
from module_office.dependencies.document_parse import get_document_parse_service
from module_office.service.document_parse import DocumentParseService
from module_office.utils.file_parse.oxide import (
    OxideConvertError,
    extract_output,
    markdown_to_office,
)
from module_office.utils.file_parse.oxide import (
    convert as oxide_convert,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _spool_upload(file: UploadFile, target: Path, chunk_size: int = 1024 * 1024) -> None:
    """将上传文件分块落盘到 target

    避免 file.file.read() 同步全量读 + write_bytes 同步写盘阻塞事件循环
    (大文件上传期间会卡死整个服务); 读走 UploadFile 异步接口, 磁盘写入放线程池
    """
    with target.open("wb") as f:
        while chunk := await file.read(chunk_size):
            await asyncio.to_thread(f.write, chunk)


@router.post(
    "/get-markdown-by-file",
    summary="根据文件路径获取Markdown内容",
)
async def get_markdown_by_file(
    file: UploadFile,
    engine: str | None = Query(
        None, description="显式指定解析引擎(如 oxide-local), 缺省按解析方案路由"
    ),
    # 【关键】自动从 Token 中解析当前登录用户的 ID，无需前端手动传
    user_id: str = Depends(get_current_user_id),
    document_parse_service: DocumentParseService = Depends(get_document_parse_service),
) -> str:
    """
    文件解析成markdown
    :param file: 上传的文件
    :param engine: 可选, 显式指定解析引擎(如 oxide-local)
    :param user_id: 当前登录用户的 ID
    :return: 解析后的Markdown内容列表
    """
    # 隔离临时目录暂存上传文件(仅保留后缀, 不用原始文件名拼路径, 防穿越/覆盖; 用完即清)
    temp_dir = Path(tempfile.mkdtemp(prefix="office_parse_src_"))
    try:
        suffix = Path(file.filename or "").suffix
        temp_file = temp_dir / f"source{suffix}"
        await _spool_upload(file, temp_file)
        return await document_parse_service.file2markdown(temp_file, engine=engine)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# --------------------------- Oxide admin 测试端点 ---------------------------
# module_office 未注册任何 user 角色默认策略, 以下 require_permission 校验
# 实际仅全局 admin 可通过(admin 策略穿透一切), 用于管理员验证
# oxide 引擎的多形态提取与 doc/xls/ppt 转格式能力。


@router.post(
    "/oxide/extract",
    summary="[admin] Oxide 提取: markdown/json(IR结构)/html/text",
)
async def oxide_extract(
    file: UploadFile,
    out: Literal["markdown", "json", "ir", "html", "text"] = Query(
        "markdown", description="输出形态: markdown/json(文档结构IR)/html/text"
    ),
    _admin_id: str = Depends(require_permission("office", "oxide", "extract")),
) -> dict:
    """用 pdf_oxide + office_oxide 提取文档, 观察各格式对 markdown/JSON 结构的支持"""
    temp_dir = Path(tempfile.mkdtemp(prefix="oxide_extract_"))
    try:
        suffix = Path(file.filename or "").suffix
        temp_file = temp_dir / f"source{suffix}"
        await _spool_upload(file, temp_file)
        return await asyncio.to_thread(extract_output, temp_file, out)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post(
    "/oxide/convert",
    summary="[admin] Oxide 转格式: doc/docx/xls/xlsx/ppt/pptx/pdf → docx/xlsx/pptx",
)
async def oxide_format_convert(
    file: UploadFile,
    target: Literal["docx", "xlsx", "pptx"] = Query(
        "docx", description="目标格式: docx/xlsx/pptx"
    ),
    markdown: str | None = Query(
        None, description="改为由 Markdown 生成目标格式(office_oxide.create_from_markdown)"
    ),
    _admin_id: str = Depends(require_permission("office", "oxide", "convert")),
) -> Response:
    """转格式测试: pdf_oxide(PDF→Office) / office_oxide(Office→Office, Markdown→Office)"""
    temp_dir = Path(tempfile.mkdtemp(prefix="oxide_convert_"))
    try:
        if markdown is not None:
            out_path = temp_dir / f"converted.{target}"
            strategy = await asyncio.to_thread(
                markdown_to_office, markdown, f".{target}", out_path
            )
            data = out_path.read_bytes()
            base_name = f"generated.{target}"
        else:
            suffix = Path(file.filename or "").suffix
            temp_file = temp_dir / f"source{suffix}"
            await _spool_upload(file, temp_file)
            try:
                data, fmt, strategy = await asyncio.to_thread(
                    oxide_convert, temp_file, target
                )
            except OxideConvertError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            base_name = f"{Path(file.filename or 'doc').stem}.{fmt}"
        filename = quote(base_name)
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "X-Convert-Strategy": strategy,
            },
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)



module_app.include_router(router, prefix="/document-parse")
