"""Office 本地解析引擎(docx/pptx, 纯标准库实现)。

MinerU 4.0 已支持 Office 原生文档, 默认走 MinerU; 本引擎作为离线兜底。
"""
from module_office.utils.file_parse.office.parser import OfficeParser

__all__ = ["OfficeParser"]
