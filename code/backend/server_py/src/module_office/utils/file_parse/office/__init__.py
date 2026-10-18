"""Office 本地解析引擎(docx/pptx, 纯标准库实现)。

MinerU 远程 API 仅支持 pdf/图片, Office 格式由本引擎本地解析兜底。
"""
from module_office.utils.file_parse.office.parser import OfficeParser

__all__ = ["OfficeParser"]
