"""AI 能力对象: 跨模块能力契约的输入输出 DTO

其他模块(module_office / module_rag / module_agent)通过
``module_ai.service`` 的能力契约调用本模块, 输入输出统一使用本文件的 DTO
(图片/音频一律以原始字节传入), 避免 langchain 与引擎实现细节外泄。
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class OcrLine(BaseModel):
    """单行文字识别结果(在线整图识别时 box 为整图矩形)"""

    text: str = Field(..., description="识别文本")
    box: list[list[float]] | None = Field(None, description="文字框坐标 [[x,y], ...]")
    score: float = Field(1.0, description="置信度(在线整图识别恒为 1.0)")


class OcrResult(BaseModel):
    """OCR 识别结果(图片与文档统一口径)"""

    text: str = Field("", description="拼接后的完整文本")
    lines: list[OcrLine] = Field(default_factory=list, description="分行结果")
    engine: str = Field("", description="实际使用的引擎标识")
    elapsed: float = Field(0.0, description="耗时(秒)")


class TranscriptSegment(BaseModel):
    """音视频转写片段(带时间轴, 供 RAG 分块记录 position.time_range)"""

    text: str = Field(..., description="片段文本")
    start: float | None = Field(None, description="起始秒")
    end: float | None = Field(None, description="结束秒")


class TranscriptResult(BaseModel):
    """音视频转写结果"""

    text: str = Field("", description="完整转写文本")
    segments: list[TranscriptSegment] = Field(
        default_factory=list, description="带时间轴的片段"
    )
    engine: str = Field("", description="实际使用的引擎标识")
    elapsed: float = Field(0.0, description="耗时(秒)")


class ChatMessage(BaseModel):
    """对话能力的最小消息结构(与具体 langchain 消息类解耦)"""

    role: str = Field(..., description="角色: system/user/assistant")
    content: str = Field(..., description="消息文本")


class ModelTypeEnum(StrEnum):
    """契约层模型类型(与内部 ModelType 取值对齐, 避免外部模块引用内部枚举)"""

    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"
    OCR = "ocr"
    ASR = "asr"
    TTS = "tts"


__all__ = [
    "ChatMessage",
    "ModelTypeEnum",
    "OcrLine",
    "OcrResult",
    "TranscriptResult",
    "TranscriptSegment",
]
