"""解析器工厂: 按引擎与后缀路由解析器"""

from pathlib import Path
from typing import ClassVar

from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.mineru import MinerUParser


class ParserFactory:
    """解析器工厂

    根据文件后缀创建对应解析器实例，统一输出 do.chunk.Chunk 列表。

    引擎说明(基线版, 解析全部走外部服务, 无本地推理依赖):
      - mineru: 唯一内置引擎(pdf/doc/docx/ppt/pptx), 调用远程 mineru.net API
        或本地 docker mineru-api, HTTP 调用零本地重型依赖。

    扩展接口(后续接入其他解析服务)：
      - 在 file_parse 下新建引擎目录(如 other_service/)，实现 BaseParser 子类；
      - 在本工厂新增注册表与 engine 分支(或在注册表内按后缀替换解析器类)即可，
        上层 service/RAG 链路无需改动。
    """

    # mineru 引擎: 后缀 -> 解析器类(MinerU 官方支持的版式文档与图片格式, 远程 API 实测)
    _MINERU_REGISTRY: ClassVar[dict[str, type[BaseParser]]] = {
        ".pdf": MinerUParser,
        ".docx": MinerUParser,
        ".doc": MinerUParser,
        ".pptx": MinerUParser,
        ".ppt": MinerUParser,
        ".png": MinerUParser,
        ".jpg": MinerUParser,
        ".jpeg": MinerUParser,
    }

    # 引擎名 -> 后缀注册表(新解析服务在此登记即可接入)
    _ENGINES: ClassVar[dict[str, dict[str, type[BaseParser]]]] = {
        "mineru": _MINERU_REGISTRY,
    }

    @classmethod
    def create(
        cls,
        file: Path,
        *,
        ocr_llm=None,
        engine: str = "mineru",
    ) -> BaseParser:
        """创建解析器

        :param file: 文件路径(按后缀路由)
        :param ocr_llm: OCR 模型(用于版式文档图片内容提取等场景)
        :param engine: 解析引擎名称，默认 mineru；新引擎在此分支扩展
        :return: BaseParser 实例
        :raises ValueError: 引擎未注册或文件后缀不受支持
        """
        registry = cls._ENGINES.get(engine)
        if registry is None:
            raise ValueError(
                f"不支持的解析引擎: {engine} (已注册: {list(cls._ENGINES.keys())})"
            )

        suffix = file.suffix.lower()
        parser_cls = registry.get(suffix)
        if parser_cls is None:
            raise ValueError(f"不支持的文件类型: {suffix} (engine={engine})")

        return parser_cls(ocr_llm=ocr_llm)
