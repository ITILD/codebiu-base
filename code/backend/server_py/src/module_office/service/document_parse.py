"""文档解析模块 document_parse 业务逻辑层"""

from pathlib import Path

from langchain_core.language_models import BaseChatModel

from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.do.chunk import Chunk
from module_office.utils.file_parse.factory import ParserFactory


class DocumentParseService:
    """文件解析服务(调用外部解析服务, 当前内置 MinerU 引擎)"""

    def __init__(self):
        """依赖注入构造器:初始化所需的数据访问对象"""
        pass

    async def file2chunk(
        self,
        file_path: Path,
        ocr_llm: BaseChatModel | None = None,
    ) -> list[Chunk]:
        """
        将文件解析为带元数据(内容类型、页码等)的 Chunk 列表

        解析引擎由 ParserFactory 按后缀路由(当前内置 mineru 外部服务,
        新解析服务在工厂注册即可接入, 本服务无需改动)。

        :param file_path: 文件路径
        :param ocr_llm: 版式文档图片内容提取的 VLM 模型(可选)
        :return: Chunk 列表
        :raises ValueError: 文件后缀不受当前引擎支持
        """
        parser: BaseParser = ParserFactory.create(file_path, ocr_llm=ocr_llm)
        return await parser.extract(file_path)

    async def file2markdown(
        self,
        file_path: Path,
        ocr_llm: BaseChatModel | None = None,
    ) -> str:
        """
        将文件解析为Markdown格式
        """
        chunks = await self.file2chunk(file_path, ocr_llm)
        markdown = "\n".join([chunk.content for chunk in chunks])

        return markdown
