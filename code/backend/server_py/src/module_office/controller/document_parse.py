"""
文件解析成markdown
"""

import logging

from fastapi import APIRouter, Depends, UploadFile

from common.config.path import DIR_TEMP
from module_authorization.dependencies.auth import get_current_user_id
from module_office.config.server import module_app
from module_office.dependencies.document_parse import get_document_parse_service
from module_office.service.document_parse import DocumentParseService

logger = logging.getLogger(__name__)

router = APIRouter()


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
    # 临时存储
    temp_file = DIR_TEMP / file.filename
    temp_file.write_bytes(file.file.read())

    return await document_parse_service.file2markdown(temp_file)


module_app.include_router(router, prefix="/document-parse")
