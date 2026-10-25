"""解析引擎注册表: 能力矩阵 + 按解析方案路由 + 构造函数降级

每个引擎声明自己真实支持的后缀与能力, 路由时按「显式引擎 / 主引擎 →
备用引擎 → 优先级」依次挑选, 后缀不匹配的引擎绝不会被选中。

MinerU 4.0 已支持 pdf/图片及 DOC/DOCX、PPT/PPTX、XLS/XLSX 等原生文档,
因此 Office 格式默认优先交给 MinerU 做版式解析; 本地 OfficeParser 作为
离线/未配置 Token 时的兜底引擎(优先级最低)。
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from module_office.do.parse import ParseAttempt, ParseContext, ParsePlan
from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.mineru import MinerUParser
from module_office.utils.file_parse.office import OfficeParser
from module_office.utils.file_parse.paddleocr import PaddleOCRParser

logger = logging.getLogger(__name__)


class EngineCapability(StrEnum):
    """引擎能力标签(用于按能力筛选, 当前主要用于展示与后续媒体路由)"""

    LAYOUT = "layout"
    TEXT = "text"
    TABLE = "table"
    FORMULA = "formula"
    OCR = "ocr"
    VLM = "vlm"
    ASR = "asr"


@dataclass(frozen=True, slots=True)
class EngineDescriptor:
    """引擎描述: 声明式支持面, 是路由的唯一依据"""

    name: str
    label: str
    suffixes: frozenset[str]
    capabilities: frozenset[EngineCapability]
    parser_cls: type[BaseParser]
    priority: int = 100


class UnsupportedFileTypeError(ValueError):
    """没有引擎可以处理该文件类型"""

    def __init__(self, suffix: str, engines: list[str]):
        self.suffix = suffix
        self.engines = engines
        super().__init__(
            f"不支持的文件类型: {suffix}(已注册引擎: {engines or '无'}), "
            "请转存为 pdf/docx/pptx 或图片后重试"
        )


class EngineRegistry:
    """解析引擎注册表(进程内单例, 通过模块级 ``engine_registry`` 使用)"""

    def __init__(self) -> None:
        self._engines: dict[str, EngineDescriptor] = {}

    def register(self, descriptor: EngineDescriptor) -> None:
        """注册引擎(同名覆盖, 便于测试替换)"""
        self._engines[descriptor.name] = descriptor

    def get(self, name: str) -> EngineDescriptor | None:
        """按名称获取引擎描述(兼容 paddle/office 旧称)"""
        alias = {"paddle": "paddleocr", "office": "office-local"}
        return self._engines.get(alias.get(name, name))

    def names(self) -> list[str]:
        """已注册引擎名(用于配置校验与错误提示)"""
        return list(self._engines)

    def describe(self) -> list[dict]:
        """能力矩阵(供后台解析配置页展示引擎支持面)"""
        return [
            {
                "name": d.name,
                "label": d.label,
                "suffixes": sorted(d.suffixes),
                "capabilities": sorted(d.capabilities),
                "priority": d.priority,
            }
            for d in sorted(self._engines.values(), key=lambda x: x.priority)
        ]

    def candidates(
        self, file: Path, plan: ParsePlan | None = None, engine: str | None = None
    ) -> list[EngineDescriptor]:
        """返回按优先级排序的候选引擎(仅保留后缀匹配的)

        :param file: 待解析文件(按后缀筛选)
        :param plan: 解析方案(主引擎/备用引擎顺序优先)
        :param engine: 显式指定引擎(优先级最高, 覆盖 plan)
        """
        suffix = file.suffix.lower()
        preferred: list[str] = []
        if engine:
            explicit = self.get(engine)
            if explicit is None:
                raise ValueError(
                    f"不支持的解析引擎: {engine} (已注册: {self.names()})"
                )
            if suffix not in explicit.suffixes:
                raise ValueError(f"不支持的文件类型: {suffix} (engine={engine})")
            preferred.append(engine)
        elif plan and plan.primary_engine and plan.primary_engine != "auto":
            preferred.append(plan.primary_engine)
        if plan:
            preferred.extend(plan.fallback_engines)

        matched = [d for d in self._engines.values() if suffix in d.suffixes]
        matched.sort(key=lambda d: d.priority)

        ordered: list[EngineDescriptor] = []
        for name in preferred:
            descriptor = self.get(name)
            if descriptor and suffix in descriptor.suffixes and descriptor not in ordered:
                ordered.append(descriptor)
        for descriptor in matched:
            if descriptor not in ordered:
                ordered.append(descriptor)
        return ordered

    def create(
        self,
        file: Path,
        ctx: ParseContext,
        *,
        plan: ParsePlan | None = None,
        engine: str | None = None,
    ) -> tuple[BaseParser, EngineDescriptor, list[ParseAttempt]]:
        """创建解析器(构造失败按候选顺序降级)

        :return: (解析器实例, 命中的引擎描述, 初始化失败的引擎尝试记录)
        :raises UnsupportedFileTypeError: 无引擎支持该后缀
        :raises RuntimeError: 全部候选引擎均构造失败(汇总原因)
        """
        candidates = self.candidates(file, plan, engine)
        if not candidates:
            raise UnsupportedFileTypeError(file.suffix.lower(), self.names())

        failed: list[ParseAttempt] = []
        errors: list[str] = []
        for descriptor in candidates:
            try:
                return descriptor.parser_cls(ctx), descriptor, failed
            except Exception as e:  # 引擎初始化失败(缺 token/服务不可达等)时降级
                logger.warning("解析引擎 %s 初始化失败: %s", descriptor.name, e)
                errors.append(f"{descriptor.name}: {e}")
                failed.append(
                    ParseAttempt(engine=descriptor.name, ok=False, error=str(e))
                )
        raise RuntimeError("全部解析引擎初始化失败: " + "; ".join(errors))


# 模块级单例: 新引擎在此登记即可接入, 上层服务无需改动
engine_registry = EngineRegistry()

# MinerU: 版式文档 / 图片 / 原生 Office 文档的整文件解析(MinerU 4.0 支持面)
engine_registry.register(
    EngineDescriptor(
        name="mineru",
        label="MinerU",
        suffixes=frozenset(
            {
                ".pdf",
                ".png",
                ".jpg",
                ".jpeg",
                ".doc",
                ".docx",
                ".ppt",
                ".pptx",
                ".xls",
                ".xlsx",
                ".rtf",
                ".odt",
                ".ods",
                ".odp",
                ".epub",
                ".ofd",
                ".html",
                ".htm",
                ".mhtml",
                ".csv",
                ".tsv",
            }
        ),
        capabilities=frozenset(
            {
                EngineCapability.LAYOUT,
                EngineCapability.TEXT,
                EngineCapability.TABLE,
                EngineCapability.FORMULA,
                EngineCapability.VLM,
            }
        ),
        parser_cls=MinerUParser,
        priority=10,
    )
)

# PaddleOCR: pdf/图片整文件 OCR(能力由 module_ai 提供)
engine_registry.register(
    EngineDescriptor(
        name="paddleocr",
        label="PaddleOCR-VL",
        suffixes=frozenset({".pdf", ".png", ".jpg", ".jpeg"}),
        capabilities=frozenset(
            {EngineCapability.LAYOUT, EngineCapability.OCR, EngineCapability.TABLE}
        ),
        parser_cls=PaddleOCRParser,
        priority=20,
    )
)

# 本地 Office: docx/pptx 纯标准库解析, 作为 MinerU 不可用时的离线兜底
engine_registry.register(
    EngineDescriptor(
        name="office-local",
        label="本地 Office 解析",
        suffixes=frozenset({".docx", ".pptx"}),
        capabilities=frozenset({EngineCapability.TEXT, EngineCapability.TABLE}),
        parser_cls=OfficeParser,
        priority=30,
    )
)
