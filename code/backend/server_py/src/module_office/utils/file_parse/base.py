"""解析器抽象基类: 统一 extract 协议

所有引擎解析器继承 BaseParser 并由 EngineRegistry 以统一构造协议
``parser_cls(ctx)`` 实例化; 需要模型能力(VLM/OCR/ASR)时只通过
``ctx`` 中的 module_ai 能力契约获取, 不直接依赖具体模型实现。
"""

from abc import ABC, abstractmethod
from pathlib import Path

from module_office.do.parse import ParseContext
from module_office.utils.file_parse.do.chunk import Chunk


class BaseParser(ABC):
    """解析器基类

    统一输出 do.chunk.Chunk 列表, 便于后续扩展其他外部解析服务。
    """

    def __init__(self, ctx: ParseContext | None = None):
        """统一构造协议: 接收解析上下文(用户ID/解析方案/能力注入)"""
        self.ctx = ctx or ParseContext()

    @property
    def user_id(self) -> str | None:
        """当前解析所属用户ID(用于解析其绑定的模型)"""
        return self.ctx.user_id

    @abstractmethod
    async def extract(self, file: Path) -> list[Chunk]:
        """将文件解析为 Chunk 列表

        :param file: 文件路径
        :return: 带元数据(内容类型、位置等)的 Chunk 列表
        """
        raise NotImplementedError
