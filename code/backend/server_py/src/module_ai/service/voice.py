"""语音服务(ASR/TTS): 统一模型入口的门面(模型能力全部通过外部服务接入)

配置解析与引擎构建委托 ModelEntryService(service/model_entry.py 统一入口):
    - model_type=asr/tts + server_type=online 的记录即为可选方案
    - engine 参数可选: 指定时精确匹配 server_type(旧值 dashscope/sherpa/qwen/local 自动归一化为 online),
      缺省时按 用户个人绑定 → 全局默认 解析
    - 引擎缓存键含配置 updated_at, 配置修改后自动重建
    - 表中无配置时抛出异常提示先添加在线语音模型
    - online 内部协议细节由 extra 分派: extra.protocol=dashscope|openai
"""
import logging
from collections.abc import AsyncIterator
from typing import Iterator, Tuple

from module_ai.do.voice import VoiceEngine
from module_ai.service.model_entry import ModelEntryService, get_model_entry
from module_ai.utils.voice.interface import ASREngine, TTSEngine

logger = logging.getLogger(__name__)


class ASRStreamSession:
    """流式 ASR 会话: 封装 ASR 流式会话的生命周期

    音频格式: 16kHz 16bit 单声道 PCM(与前端麦克风采集一致)
    """

    # 流式 ASR 期望的 PCM 采样率(固定 16kHz)
    SAMPLE_RATE = 16000

    def __init__(self, asr: ASREngine, stream):
        self._asr = asr
        self._stream = stream

    async def accept(self, pcm_bytes: bytes) -> None:
        """送入一帧 16kHz 16bit 单声道 PCM"""
        await self._asr.stream_accept_async(self._stream, pcm_bytes, self.SAMPLE_RATE)

    async def result(self, is_final: bool = False) -> str:
        """获取当前识别文本"""
        return await self._asr.stream_result_async(self._stream, is_final=is_final)

    async def finish(self) -> str:
        """结束识别: 返回最终文本"""
        return await self.result(is_final=True)

    async def close(self) -> None:
        """销毁流式会话(幂等, 异常静默)"""
        try:
            await self._asr.stream_destroy_async(self._stream)
        except Exception:
            pass
        self._stream = None


class VoiceService:
    """语音服务门面: asr/tts 引擎的解析/构建/缓存统一委托 ModelEntryService"""

    def __init__(self, model_entry: ModelEntryService | None = None):
        """依赖注入构造器: 统一入口缺省取全局单例"""
        self._entry = model_entry or get_model_entry()

    async def get_engine(
        self, model_type: str, engine: VoiceEngine | None = None, user_id: str | None = None
    ) -> ASREngine | TTSEngine:
        """按模型类型获取引擎实例(asr/tts 通用)

        :param model_type: 模型类型(asr/tts)
        :param engine: 指定方案(None 时按 用户绑定/全局配置 自动选择)
        :param user_id: 当前用户ID(未指定方案时用户绑定优先)
        """
        return await self._entry.get_engine(
            model_type, server_type=engine.value if engine else None, user_id=user_id
        )

    async def get_asr(
        self, engine: VoiceEngine | None = None, user_id: str | None = None
    ) -> ASREngine:
        """
        获取 ASR 引擎(按用户绑定/模型配置选择方案)
        :param engine: 指定方案(None 时自动选择)
        :param user_id: 当前用户ID(用户绑定优先)
        """
        result = await self.get_engine("asr", engine, user_id)
        return result  # type: ignore[return-value]

    async def create_asr_stream(
        self, engine: VoiceEngine | None = None, user_id: str | None = None
    ) -> ASRStreamSession:
        """创建流式 ASR 会话

        :raises Exception: ASR 引擎/流式会话初始化失败时抛出(交由调用方处理)
        """
        asr = await self.get_asr(engine, user_id)
        stream = await asr.create_stream_async()
        return ASRStreamSession(asr, stream)

    async def get_tts(
        self, engine: VoiceEngine | None = None, user_id: str | None = None
    ) -> TTSEngine:
        """
        获取 TTS 引擎(按用户绑定/模型配置选择方案)
        :param engine: 指定方案(None 时自动选择)
        :param user_id: 当前用户ID(用户绑定优先)
        """
        result = await self.get_engine("tts", engine, user_id)
        return result  # type: ignore[return-value]

    async def asr(
        self, audio_bytes: bytes, engine: VoiceEngine | None = None, user_id: str | None = None
    ) -> str:
        """语音识别(未指定 engine 时按用户绑定/全局配置自动选择方案)"""
        asr = await self.get_asr(engine, user_id)
        return asr.recognize(audio_bytes)

    async def tts(
        self,
        text: str,
        engine: VoiceEngine | None = None,
        speaker: int = 0,
        speed: float = 1.0,
        sample_rate: int = 22050,
        user_id: str | None = None,
    ) -> Tuple[bytes, int]:
        """语音合成(未指定 engine 时按用户绑定/全局配置自动选择方案)"""
        tts = await self.get_tts(engine, user_id)
        # 在线引擎优先走异步路径(dashscope 协议经 CosyVoice WebSocket, HTTP 端点已不支持)
        if hasattr(tts, "synthesize_async"):
            return await tts.synthesize_async(text, speaker, speed, sample_rate)  # type: ignore[attr-defined]
        return tts.synthesize(text, speaker, speed, sample_rate)

    async def tts_stream(
        self,
        text: str,
        engine: VoiceEngine | None = None,
        speaker: int = 0,
        speed: float = 1.0,
        sample_rate: int = 22050,
        user_id: str | None = None,
    ) -> Tuple[Iterator[Tuple[bytes, int, bool]], VoiceEngine]:
        """
        流式语音合成(同步 iterator 路径)
        :return: (PCM 分块迭代器, 实际生效的引擎)
        """
        # 先同步解析引擎(生成器内不能 await)
        tts = await self.get_tts(engine, user_id)
        effective = await self.effective_engine("tts", engine, user_id)
        return tts.synthesize_stream(text, speaker, speed, sample_rate), effective

    async def tts_stream_async(
        self,
        text: str,
        engine: VoiceEngine | None = None,
        speaker: int = 0,
        speed: float = 1.0,
        sample_rate: int = 22050,
        user_id: str | None = None,
    ) -> Tuple[AsyncIterator[Tuple[bytes, int, bool]] | Iterator[Tuple[bytes, int, bool]], VoiceEngine, bool]:
        """
        流式语音合成(优先真异步路径)
        :return: (分块迭代器[Async|Sync], 实际生效引擎, 是否异步迭代器)
        """
        tts = await self.get_tts(engine, user_id)
        effective = await self.effective_engine("tts", engine, user_id)
        # 异步生成器函数调用时不会执行方法体, NotImplementedError 要到首个 __anext__ 才抛出,
        # 因此通过"是否覆写基类方法"判断真异步支持(如仅同步实现的引擎则回退同步切片路径)
        if type(tts).synthesize_stream_async is not TTSEngine.synthesize_stream_async:
            return tts.synthesize_stream_async(text, speaker, speed, sample_rate), effective, True
        return tts.synthesize_stream(text, speaker, speed, sample_rate), effective, False

    async def effective_engine(
        self, model_type: str, engine: VoiceEngine | None, user_id: str | None = None
    ) -> VoiceEngine:
        """计算实际生效方案(恒为 online; 供响应回显真实方案)

        :param model_type: 模型类型(asr/tts)
        :param engine: 请求指定的方案(None 时按模型配置自动选择)
        :return: 实际生效的引擎方案
        """
        return engine or VoiceEngine.ONLINE
