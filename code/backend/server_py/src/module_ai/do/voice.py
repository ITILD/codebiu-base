"""AI 模型接入模块 voice 表模型与请求/响应体定义"""

from enum import Enum

from pydantic import BaseModel, Field


class VoiceEngine(str, Enum):
    """语音引擎方案: 仅保留 online(远程API或本地vllm发布, 协议细节放 extra.protocol)

    模型能力全部通过外部服务接入, 本地推理(sherpa/qwen onnx)已下线;
    历史值 dashscope/sherpa/qwen/local 由 resolve_engine 归一化(旧请求兼容窗口)
    """

    ONLINE = "online"


def resolve_engine(raw: str | None) -> VoiceEngine | None:
    """解析 engine 参数并归一化为 online 方案(历史值兼容映射)

    - 空/None 返回 None, 由模型配置自动选择
    - 旧值兼容: dashscope/sherpa/qwen/local 一律按 online 处理(本地方案已下线)
    - 无效值回落 None 交由上层按模型配置自动选择
    """
    if not raw or not raw.strip():
        return None
    raw = raw.strip().lower()
    if raw in ("online", "dashscope", "sherpa", "qwen", "local"):
        return VoiceEngine.ONLINE
    return None


class TTSRequest(BaseModel):
    """语音合成(TTS)请求模型"""

    text: str = Field(..., description="需要合成的文本内容")
    engine: str | None = Field(
        None, description="TTS 引擎方案: online(兼容旧值 dashscope/sherpa/qwen/local, 缺省按模型配置自动选择)"
    )
    speaker: int = Field(0, description="说话人 ID(多说话人模型使用)")
    speed: float = Field(1.0, description="语速倍率")
    sample_rate: int = Field(22050, description="目标采样率")


class ASRResponse(BaseModel):
    """语音识别(ASR)结果"""

    text: str = Field("", description="识别出的文本")
    engine: VoiceEngine = Field(VoiceEngine.ONLINE, description="使用的引擎方案(online)")
    elapsed: float = Field(0.0, description="耗时(秒)")


class ASRStreamMessage(BaseModel):
    """ASR 流式识别消息(WebSocket)"""

    text: str = Field("", description="当前识别文本")
    is_final: bool = Field(False, description="是否为最终结果")
    engine: VoiceEngine = Field(VoiceEngine.ONLINE, description="使用的引擎方案(online)")
