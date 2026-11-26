"""Oxide 解析引擎(pdf_oxide + office_oxide)。

本地解析 pdf/doc/docx/xls/xlsx/ppt/pptx(含旧版二进制格式), 并提供
docx/xlsx/pptx 转格式能力。MinerU 不可用时的离线兜底, 优先级高于在线 OCR。
"""
from module_office.utils.file_parse.oxide.convert import (
    OxideConvertError,
    convert,
    markdown_to_office,
)
from module_office.utils.file_parse.oxide.parser import (
    OxideParser,
    OxideParserPlain,
    extract_output,
)

__all__ = [
    "OxideParser",
    "OxideParserPlain",
    "OxideConvertError",
    "convert",
    "extract_output",
    "markdown_to_office",
]
