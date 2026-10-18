"""解析器抽象基类: 统一 extract 协议"""

from abc import ABC, abstractmethod
from pathlib import Path

from module_office.utils.file_parse.do.chunk import Chunk


class BaseParser(ABC):
    """解析器基类

    所有文件解析器需继承此类并实现 extract 方法，
    统一输出 do.chunk.Chunk 列表，便于后续扩展其他外部解析服务(如 MinerU 之外的引擎)。

    统一构造协议: 工厂以 ``parser_cls(ocr_llm=...)`` 实例化全部解析器,
    引擎子类按需保存或忽略 ocr_llm。
    """

    def __init__(self, ocr_llm=None):
        self.ocr_llm = ocr_llm

    @abstractmethod
    async def extract(self, file: Path) -> list[Chunk]:
        """将文件解析为 Chunk 列表

        :param file: 文件路径
        :return: 带元数据(内容类型、位置等)的 Chunk 列表
        """
        raise NotImplementedError
