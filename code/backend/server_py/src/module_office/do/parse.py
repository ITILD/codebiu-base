"""文档解析对象: 解析方案 / 运行时上下文 / 尝试记录 / 解析结果

本文件只承载数据结构(DO), 不含解析逻辑; 跨模块调用统一走
``module_office.service.document_parse.DocumentParseService``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from module_office.utils.file_parse.do.chunk import Chunk

if TYPE_CHECKING:
    # 仅类型标注使用, 避免 office 的 do 层在导入期加载 module_ai 的实现依赖
    from module_ai.service.llm import VisionCapability
    from module_ai.service.ocr import OcrCapability


class ParsePlan(BaseModel):
    """解析方案(由后台「RAG 解析配置」持久化, 调用方也可按需临时构造)"""

    primary_engine: str = Field(
        "auto", description="主引擎: auto/mineru/paddleocr/office-local/media"
    )
    fallback_engines: list[str] = Field(
        default_factory=list, description="备用引擎, 顺序即优先级(构造失败时依次降级)"
    )
    media_policy: dict[str, str] = Field(
        default_factory=dict,
        description="媒体策略: image=ocr|vlm|both|off, audio=asr, video=asr",
    )
    limits: dict[str, int] = Field(
        default_factory=dict, description="上限: max_pages/max_duration/max_size_mb"
    )


@dataclass(slots=True)
class ParseContext:
    """一次解析的运行时上下文(注入能力契约, 避免 office 依赖 ai 内部实现)"""

    user_id: str | None = None
    vision: VisionCapability | None = None
    ocr: OcrCapability | None = None
    plan: ParsePlan = field(default_factory=ParsePlan)


class ParseAttempt(BaseModel):
    """单个引擎的尝试记录, 用于前端展示与问题定位"""

    engine: str = Field(..., description="引擎标识")
    ok: bool = Field(False, description="是否成功")
    error: str | None = Field(None, description="失败原因")


class ParseResult(BaseModel):
    """解析结果(引擎 + 尝试链路 + 分块)"""

    chunks: list[Chunk] = Field(default_factory=list, description="解析出的分块")
    engine: str = Field("", description="最终成功的引擎标识")
    attempts: list[ParseAttempt] = Field(
        default_factory=list, description="引擎尝试链路(按顺序)"
    )
    source: Path | None = Field(None, description="源文件路径")
