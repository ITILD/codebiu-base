"""语音引擎抽象接口(ASR/TTS)"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator


class ASREngine(ABC):
    """ASR 引擎抽象接口"""

    @abstractmethod
    def recognize(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """离线识别完整音频，返回文本

        Args:
            audio_bytes: 音频原始字节(WAV/MP3 等可被 soundfile 解码的格式)
            sample_rate: 期望采样率
        """
        ...

    def create_stream(self):
        """创建一个在线流式识别会话，返回会话对象"""
        raise NotImplementedError("当前 ASR 引擎不支持流式识别")

    def stream_accept(self, stream, samples, sample_rate: int = 16000) -> str:
        """向流式会话送入一帧 PCM 样本，返回当前增量文本(可选)"""
        raise NotImplementedError("当前 ASR 引擎不支持流式识别")

    def stream_result(self, stream, is_final: bool = False) -> str:
        """获取流式会话的当前文本"""
        raise NotImplementedError("当前 ASR 引擎不支持流式识别")

    def stream_destroy(self, stream) -> None:
        """销毁流式会话"""
        pass

    # ---------- 异步流式方法族(默认转发同步版本; 引擎可覆写为真异步实现) ----------

    async def create_stream_async(self):
        """创建异步流式识别会话(默认在线程池执行同步 create_stream)"""
        return await asyncio.to_thread(self.create_stream)

    async def stream_accept_async(self, stream, samples, sample_rate: int = 16000) -> str:
        """异步送入一帧 PCM 样本(默认在线程池执行同步 stream_accept)"""
        return await asyncio.to_thread(self.stream_accept, stream, samples, sample_rate)

    async def stream_result_async(self, stream, is_final: bool = False) -> str:
        """异步获取当前识别文本(默认在线程池执行同步 stream_result)"""
        return await asyncio.to_thread(self.stream_result, stream, is_final)

    async def stream_destroy_async(self, stream) -> None:
        """异步销毁流式会话(默认在线程池执行同步 stream_destroy)"""
        await asyncio.to_thread(self.stream_destroy, stream)


class TTSEngine(ABC):
    """TTS 引擎抽象接口"""

    @abstractmethod
    def synthesize(
        self, text: str, speaker: int = 0, speed: float = 1.0, sample_rate: int = 22050
    ) -> tuple[bytes, int]:
        """合成完整音频

        Returns:
            (pcm_int16_bytes, sample_rate)
        """
        ...

    def synthesize_stream(
        self, text: str, speaker: int = 0, speed: float = 1.0, sample_rate: int = 22050
    ) -> Iterator[tuple[bytes, int, bool]]:
        """流式合成音频，yield (pcm_int16_bytes, sample_rate, is_final)

        默认实现：先合成完整音频，再按 200ms 切片流式返回。
        子类可重写以实现真正的逐句流式合成。
        """
        pcm, sr = self.synthesize(text, speaker, speed, sample_rate)
        # 200ms 一片(int16 单声道)
        chunk_bytes = int(sr * 0.2) * 2
        total = len(pcm)
        offset = 0
        while offset < total:
            chunk = pcm[offset : offset + chunk_bytes]
            offset += chunk_bytes
            yield chunk, sr, offset >= total

    def synthesize_stream_async(
        self, text: str, speaker: int = 0, speed: float = 1.0, sample_rate: int = 22050
    ) -> AsyncIterator[tuple[bytes, int, bool]]:
        """异步流式合成(真流式引擎覆写; 默认不支持, controller 回退同步 iterator 路径)"""
        raise NotImplementedError("当前 TTS 引擎不支持异步流式合成")
