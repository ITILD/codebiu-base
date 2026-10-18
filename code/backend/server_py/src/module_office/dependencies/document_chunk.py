"""文档解析模块 document_chunk FastAPI 依赖注入"""

from fastapi import Depends
from module_office.utils.document_chunk.prompt import DocumentChunkPrompt
from module_office.service.document_chunk import DocumentChunkService



def get_document_chunk_prompt() -> DocumentChunkPrompt:
    """文档分块提示词工厂(FastAPI依赖注入)"""
    return DocumentChunkPrompt()

def get_document_chunk_service(
    document_chunk_prompt: DocumentChunkPrompt = Depends(get_document_chunk_prompt),
) -> DocumentChunkService:
    """文档分块服务工厂(FastAPI依赖注入)"""
    return DocumentChunkService(document_chunk_prompt)
