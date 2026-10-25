"""文档解析模块 document_parse FastAPI 依赖注入"""

from module_ai.dependencies.llm import get_vision_service
from module_ai.dependencies.ocr import get_ocr_service
from module_office.service.document_parse import DocumentParseService


def get_document_parse_service() -> DocumentParseService:
    """文档解析服务工厂(FastAPI依赖注入)

    显式注入 module_ai 的视觉/OCR 能力, office 内部不再直接创建模型服务。
    """
    return DocumentParseService(
        vision=get_vision_service(), ocr=get_ocr_service()
    )
