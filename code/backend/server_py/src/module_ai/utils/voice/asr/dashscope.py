"""阿里云百炼(DashScope) 在线 ASR 引擎实现

通过 DashScope 同步多模态接口调用 Qwen3-ASR-Flash 等在线语音识别模型,
音频以 base64 Data URL 内联上传(编码后需 <10MB)。

引擎配置来源优先级:
    1. model_config 表(model_type=asr, server_type=dashscope)的 model/url/api_key/extra 字段
    2. 类内默认值回落(qwen3-asr-flash + 官方接口地址)

extra 可选键:
    - language: 音频语种提示(zh/en/ja/..., 不指定则自动检测)
    - enable_itn: 是否启用逆文本正则化(仅中英文, 默认 False)
    - timeout: 请求超时秒数(默认 60)
"""
import base64
import logging

import httpx

from module_ai.utils.voice.interface import ASREngine

logger = logging.getLogger(__name__)

# DashScope 同步多模态生成接口(ASR)
_DASHSCOPE_ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# 默认请求超时(秒)
_DEFAULT_TIMEOUT = 60

# 音频魔数 -> MIME(用于构造 Data URL)
_AUDIO_MIME_RULES: tuple[tuple[bytes, str], ...] = (
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
    (b"\xff\xf3", "audio/mpeg"),
    (b"\xff\xf2", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"RIFF", "audio/wav"),
)


def _detect_audio_mime(audio_bytes: bytes) -> str:
    """按文件魔数粗略判断音频 MIME 类型(默认 wav)"""
    for magic, mime in _AUDIO_MIME_RULES:
        if audio_bytes.startswith(magic):
            return mime
    return "audio/wav"


def _detect_audio_format(audio_bytes: bytes) -> str:
    """按文件魔数映射为 WS 上行格式名(默认 pcm)"""
    if audio_bytes.startswith(b"RIFF"):
        return "wav"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if audio_bytes.startswith(b"OggS"):
        return "opus"
    return "pcm"


def _run_sync(coro):
    """在线程中新事件循环执行协程(兼容已有运行中事件循环的调用场景)"""
    import asyncio
    import threading

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict = {}

    def _runner():
        try:
            result["value"] = asyncio.run(coro)
        except Exception as e:  # noqa: BLE001 - 原样抛给调用方
            result["error"] = e

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


class DashscopeASR(ASREngine):
    """阿里云在线 ASR 引擎(Qwen3-ASR-Flash, 非实时一句话识别)"""

    def __init__(self, conf: dict | None = None):
        """
        :param conf: 动态配置(model_config 映射), 可含:
            - model: 在线模型名(默认 qwen3-asr-flash)
            - url: DashScope ASR 接口地址
            - api_key: 百炼 API Key(必填, 缺失时报错提示)
            - language/enable_itn/timeout: 见模块 docstring
        """
        self._conf = conf or {}

    @property
    def _api_key(self) -> str:
        api_key = str(self._conf.get("api_key") or "").strip()
        if not api_key:
            raise RuntimeError("DashScope ASR 缺少 api_key: 请在模型配置中填写百炼 API Key")
        return api_key

    def _build_payload(self, audio_bytes: bytes, sample_rate: int) -> dict:
        """构建 DashScope 多模态识别请求体"""
        data_uri = f"data:{_detect_audio_mime(audio_bytes)};base64,{base64.b64encode(audio_bytes).decode()}"
        payload: dict = {
            "model": str(self._conf.get("model") or "qwen3-asr-flash"),
            "input": {
                "messages": [
                    {"role": "user", "content": [{"audio": data_uri}]},
                ],
            },
        }
        # 语种提示/ITN 为可选参数
        asr_options: dict = {}
        if self._conf.get("language"):
            asr_options["language"] = str(self._conf["language"])
        if "enable_itn" in self._conf:
            asr_options["enable_itn"] = bool(self._conf["enable_itn"])
        if asr_options:
            payload["parameters"] = {"asr_options": asr_options}
        return payload

    @staticmethod
    def _parse_text(result: dict) -> str:
        """解析响应中的识别文本"""
        choices = (result.get("output") or {}).get("choices") or []
        for choice in choices:
            content = (choice.get("message") or {}).get("content") or []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    return str(item["text"]).strip()
        return ""

    def _recognize_ws(self, audio_bytes: bytes, sample_rate: int) -> str:
        """仅支持 WS 推理的流式模型(如 qwen-audio-3.1-asr-flash-streaming)同步识别:
        复用实时 WS 会话整段送入并收割最终文本(在独立事件循环中执行)"""
        from module_ai.utils.voice.dashscope_ws import DashscopeRealtimeASRStream

        ws_conf = dict(self._conf)
        url = str(ws_conf.get("url") or "")
        ws_conf["url"] = url if url.startswith(("ws://", "wss://")) else None
        ws_conf["format"] = _detect_audio_format(audio_bytes)
        ws_conf["sample_rate"] = int(self._conf.get("sample_rate") or sample_rate)

        async def _run() -> str:
            stream = DashscopeRealtimeASRStream(ws_conf)
            try:
                await stream.start()
                await stream.accept(audio_bytes)
                await stream.finish()
                return await stream.text()
            finally:
                await stream.close()

        text = _run_sync(_run())
        if not text:
            raise RuntimeError("DashScope ASR 未返回识别文本(WS 整段识别为空)")
        return text

    def recognize(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """上传完整音频并识别为文本(配置 url 为 ws/wss 时走 WS 整段识别)"""
        if str(self._conf.get("url") or "").startswith(("ws://", "wss://")):
            return self._recognize_ws(audio_bytes, sample_rate)
        payload = self._build_payload(audio_bytes, sample_rate)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = float(self._conf.get("timeout") or _DEFAULT_TIMEOUT)
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(str(self._conf.get("url") or _DASHSCOPE_ASR_URL), headers=headers, json=payload)
        except httpx.HTTPError as e:
            raise RuntimeError(f"DashScope ASR 请求失败: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(f"DashScope ASR 请求失败({resp.status_code}): {resp.text[:500]}")
        text = self._parse_text(resp.json())
        if not text:
            raise RuntimeError(f"DashScope ASR 未返回识别文本: {resp.text[:500]}")
        return text
