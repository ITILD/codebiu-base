"""
文件解析成markdown
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile

from module_authorization.dependencies.auth import get_current_user_id
from module_office.config.server import module_app
from module_office.dependencies.document_parse import get_document_parse_service
from module_office.service.document_parse import DocumentParseService

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
    # 【关键】自动从 Token 中解析当前登录用户的 ID，无需前端手动传
    user_id: str = Depends(get_current_user_id),
    document_parse_service: DocumentParseService = Depends(get_document_parse_service),
) -> str:
    """
    文件解析成markdown
    :param file: 上传的文件
    :param user_id: 当前登录用户的 ID
    :return: 解析后的Markdown内容列表
    """
    # 隔离临时目录暂存上传文件(仅保留后缀, 不用原始文件名拼路径, 防穿越/覆盖; 用完即清)
    temp_dir = Path(tempfile.mkdtemp(prefix="office_parse_src_"))
    try:
        suffix = Path(file.filename or "").suffix
        temp_file = temp_dir / f"source{suffix}"
        await _spool_upload(file, temp_file)
        return await document_parse_service.file2markdown(temp_file)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


module_app.include_router(router, prefix="/document-parse")
