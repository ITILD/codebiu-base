# -*- coding: utf-8 -*-
"""module_ai 在线协议引擎(dashscope HTTP)标准测试

覆盖:
- 类型映射: server_types_for 对 asr/tts 仅 online, ocr 仅 dashscope, vad/denoise 已下线返回空
- 引擎归一化: 旧 engine 值 dashscope/sherpa/qwen/local -> online, 空值/无效值 -> None
- 统一入口注册表: ModelEntryService._BUILDERS 将 asr/tts/ocr 构建为在线引擎并展平 extra
- DashscopeASR/DashscopeTTS/DashscopeOCR/OXROnline: 请求体构建与响应解析(httpx 全局打桩)
- OcrService 多配置降级链: 前一条引擎失败时自动切换下一条

说明: 本地推理(sherpa/qwen)已全部下线, 语音引擎仅保留 online 方案(协议细节由 extra.protocol
分派); OCR 按 server_type/extra.protocol 分派 DashscopeOCR / PaddleOCROnline / OXROnline。
"""

import asyncio
import base64
import json
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from module_ai.do.voice import VoiceEngine, resolve_engine
from module_ai.service.model_config import ModelEntryService
from module_ai.service.ocr import OcrService
from module_ai.utils.llm.types import ModelServerType, ModelType, server_types_for
from module_ai.utils.ocr.dashscope import DashscopeOCR
from module_ai.utils.ocr.oxr import OXROnline
from module_ai.utils.voice.asr.dashscope import DashscopeASR
from module_ai.utils.voice.asr.online import OnlineASR
from module_ai.utils.voice.audio import pcm_to_wav_bytes, to_pcm16
from module_ai.utils.voice.tts.dashscope import DashscopeTTS
from module_ai.utils.voice.tts.online import OnlineTTS


# ==================== httpx 打桩(零外部依赖) ====================
class _FakeResponse:
    """httpx.Response 桩: 预设 JSON/二进制内容"""

    def __init__(self, payload: dict | None = None, content: bytes = b"", status_code: int = 200):
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


class _FakeHttpClient:
    """httpx.Client 桩: 记录请求并按序返回预设响应(类属性 last 取最近实例)"""

    last: "_FakeHttpClient | None" = None

    def __init__(self, responses: list[_FakeResponse], **kwargs):
        self.responses = list(responses)
        self.calls: list[dict] = []
        type(self).last = self

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def post(
        self,
        url: str,
        headers: dict | None = None,
        json: dict | None = None,
        data=None,
        files=None,
        **kw,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "method": "post",
                "url": url,
                "headers": headers,
                "json": json,
                "data": data,
                "files": files,
            }
        )
        return self.responses.pop(0)

    def get(self, url: str, **kw) -> _FakeResponse:
        self.calls.append({"method": "get", "url": url})
        return self.responses.pop(0)


def _patch_httpx(monkeypatch, responses: list[_FakeResponse]) -> None:
    """全局替换 httpx.Client 为打桩工厂(测试结束自动还原)"""
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeHttpClient(responses, **kw))


# ==================== 类型映射与引擎注册 ====================
def test_server_types_for_remote_engines():
    """asr/tts 仅 online 单方案; ocr 为 dashscope+online 双方案; vad/denoise 已下线返回空列表"""
    assert server_types_for(ModelType.ASR) == [ModelServerType.ONLINE]
    assert server_types_for("tts") == [ModelServerType.ONLINE]
    assert server_types_for("ocr") == [ModelServerType.DASHSCOPE, ModelServerType.ONLINE]
    assert server_types_for("vad") == []
    assert server_types_for("denoise") == []


def test_voice_engine_legacy_normalize():
    """旧 engine 值应归一化为 online: dashscope/sherpa/qwen/local 一律按在线方案处理"""
    assert resolve_engine("dashscope") is VoiceEngine.ONLINE
    assert resolve_engine("sherpa") is VoiceEngine.ONLINE
    assert resolve_engine("qwen") is VoiceEngine.ONLINE
    assert resolve_engine("local") is VoiceEngine.ONLINE
    assert resolve_engine("online") is VoiceEngine.ONLINE
    # 空值/无效值返回 None: 交由模型配置自动选择
    assert resolve_engine(None) is None
    assert resolve_engine("") is None
    assert resolve_engine("  ") is None
    assert resolve_engine("unknown-engine") is None


def test_model_entry_builders_registered():
    """统一模型入口注册表: asr/tts/ocr 应构建在线引擎实例, extra 展平进引擎配置

    OCR 按方案分派: server_type=dashscope → DashscopeOCR,
    extra.protocol=oxr → OXROnline, 其余(默认 online) → PaddleOCROnline
    """
    from module_ai.utils.ocr.paddle_online import PaddleOCROnline

    def _build(model_type: str, server_type: str | None = None, extra: dict | None = None):
        config = SimpleNamespace(
            model_type=model_type, model="m-1", server_type=server_type,
            extra=extra or {"protocol": "openai", "api_key": "sk-test"},
            api_key="", url=None, timeout=60,
        )
        return ModelEntryService._BUILDERS[model_type](config)

    asr = _build("asr")
    tts = _build("tts")
    ocr_default = _build("ocr")
    ocr_dashscope = _build("ocr", server_type=ModelServerType.DASHSCOPE)
    ocr_oxr = _build("ocr", server_type=ModelServerType.ONLINE, extra={"protocol": "oxr"})
    assert isinstance(asr, OnlineASR)
    assert isinstance(tts, OnlineTTS)
    assert isinstance(ocr_default, PaddleOCROnline), "OCR 未指定方案时默认 online(PaddleOCR 云 API)"
    assert isinstance(ocr_dashscope, DashscopeOCR), "OCR 指定 dashscope 方案应构建百炼引擎"
    assert isinstance(ocr_oxr, OXROnline), "OCR extra.protocol=oxr 应构建 OXR 引擎"
    # extra 展平: 协议/模型键进入引擎配置(顶层字段回填, extra 同名键优先)
    assert asr._conf["protocol"] == "openai"
    assert ocr_default._conf["model"] == "m-1"


# ==================== DashscopeASR ====================
def test_dashscope_asr_recognize(monkeypatch):
    """ASR: base64 Data URL 上传 + 响应文本解析 + asr_options 参数透传"""
    _patch_httpx(
        monkeypatch,
        [_FakeResponse({"output": {"choices": [{"message": {"content": [{"text": "你好世界"}]}}]}})],
    )
    engine = DashscopeASR({"api_key": "sk-test", "language": "zh", "enable_itn": True})
    text = engine.recognize(b"RIFF0000WAVE", sample_rate=16000)
    assert text == "你好世界"

    call = _FakeHttpClient.last.calls[0]
    assert call["json"]["model"] == "qwen3-asr-flash"
    audio = call["json"]["input"]["messages"][0]["content"][0]["audio"]
    assert audio.startswith("data:audio/wav;base64,")
    assert call["json"]["parameters"]["asr_options"] == {"language": "zh", "enable_itn": True}
    assert call["headers"]["Authorization"] == "Bearer sk-test"


def test_dashscope_asr_missing_api_key():
    """ASR: 缺少 api_key 应给出可操作的错误提示(不发网络请求)"""
    with pytest.raises(RuntimeError, match="api_key"):
        DashscopeASR({}).recognize(b"RIFF0000WAVE")


def test_dashscope_asr_http_error(monkeypatch):
    """ASR: 服务端报错应抛出含状态码与响应体的 RuntimeError"""
    _patch_httpx(monkeypatch, [_FakeResponse({"error": "invalid key"}, status_code=401)])
    with pytest.raises(RuntimeError, match="401"):
        DashscopeASR({"api_key": "bad"}).recognize(b"RIFF0000WAVE")


# ==================== DashscopeTTS ====================
def _make_wav() -> bytes:
    """构造 22050Hz 的真实 WAV 字节(供打桩响应/解码验证)"""
    samples = (np.sin(np.linspace(0, 440 * 2 * np.pi, 2205)) * 0.5).astype("float32")
    return pcm_to_wav_bytes(to_pcm16(samples), 22050)


def test_dashscope_tts_synthesize(monkeypatch):
    """TTS: 非流式返回音频 URL 时自动下载并解码为 PCM"""
    wav_bytes = _make_wav()
    _patch_httpx(
        monkeypatch,
        [
            _FakeResponse({"output": {"audio": {"url": "https://example.com/a.wav"}}}),
            _FakeResponse(content=wav_bytes),
        ],
    )
    engine = DashscopeTTS({"api_key": "sk-test", "voice": "longxiaochun"})
    pcm, sr = engine.synthesize("你好", sample_rate=22050)
    assert sr == 22050
    assert len(pcm) > 0

    post, get = _FakeHttpClient.last.calls
    assert post["json"]["model"] == "cosyvoice-v2"
    assert post["json"]["input"]["voice"] == "longxiaochun"
    assert post["json"]["input"]["format"] == "wav"
    assert get["url"] == "https://example.com/a.wav"


def test_dashscope_tts_base64_data_fallback(monkeypatch):
    """TTS: 响应直接携带 base64 音频数据时无需二次下载"""
    wav_bytes = _make_wav()
    _patch_httpx(
        monkeypatch,
        [_FakeResponse({"output": {"audio": {"data": base64.b64encode(wav_bytes).decode()}}})],
    )
    pcm, sr = DashscopeTTS({"api_key": "sk-test"}).synthesize("hi", sample_rate=22050)
    assert sr == 22050
    assert len(pcm) > 0
    assert len(_FakeHttpClient.last.calls) == 1, "base64 数据路径不应再发起下载请求"


def test_dashscope_tts_missing_api_key():
    """TTS: 缺少 api_key 应给出可操作的错误提示"""
    with pytest.raises(RuntimeError, match="api_key"):
        DashscopeTTS({}).synthesize("你好")


# ==================== DashscopeOCR ====================
def test_dashscope_ocr_recognize(monkeypatch):
    """OCR: PNG Data URL 上传 + 结果与本地流水线同构(box 为整图矩形)"""
    _patch_httpx(
        monkeypatch,
        [_FakeResponse({"output": {"choices": [{"message": {"content": [{"text": "识别文本"}]}}]}})],
    )
    image = np.full((10, 20, 3), 255, dtype="uint8")
    result = DashscopeOCR({"api_key": "sk-test", "model": "qwen-vl-ocr-latest"}).recognize(image)
    assert result["results"][0]["text"] == "识别文本"
    assert result["results"][0]["box"] == [[0, 0], [20, 0], [20, 10], [0, 10]]
    assert result["results"][0]["score"] == 1.0
    assert result["engine"] == "dashscope"

    call = _FakeHttpClient.last.calls[0]
    assert call["json"]["model"] == "qwen-vl-ocr-latest"
    image_uri = call["json"]["input"]["messages"][0]["content"][0]["image"]
    assert image_uri.startswith("data:image/png;base64,")


def test_dashscope_ocr_missing_api_key():
    """OCR: 缺少 api_key 应给出可操作的错误提示"""
    with pytest.raises(RuntimeError, match="api_key"):
        DashscopeOCR({}).recognize(np.zeros((4, 4, 3), dtype="uint8"))


# ==================== OXROnline ====================
def test_oxr_parse_document(monkeypatch):
    """OXR: multipart 上传 + 免费接口默认 dummy Key + outputs.markdown 抽取"""
    _patch_httpx(
        monkeypatch,
        [_FakeResponse({"code": 0, "data": {"result": {"outputs": {"markdown": "# 标题\n\n正文"}}}})],
    )
    text = OXROnline({}).parse_document(b"%PDF-1.4", "sample.pdf")
    assert text == "# 标题\n\n正文"

    call = _FakeHttpClient.last.calls[0]
    assert call["url"] == "https://free-oxr.somark.cn/api/v1/parse/sync"
    assert call["data"]["api_key"] == "dummy"
    assert call["data"]["output_formats"] == ["markdown"]
    assert call["files"]["file"][1] == b"%PDF-1.4"


def test_oxr_recognize_returns_paddle_like_result(monkeypatch):
    """OXR: 图片识别结果与本地流水线同构(box 为整图矩形)"""
    _patch_httpx(
        monkeypatch,
        [_FakeResponse({"code": 0, "data": {"result": {"outputs": {"markdown": "识别文本"}}}})],
    )
    image = np.full((10, 20, 3), 255, dtype="uint8")
    result = OXROnline({}).recognize(image)
    assert result["results"][0]["text"] == "识别文本"
    assert result["results"][0]["box"] == [[0, 0], [20, 0], [20, 10], [0, 10]]
    assert result["engine"] == "oxr"


def test_oxr_error_code(monkeypatch):
    """OXR: 响应 code 非 0 应抛出含服务端消息的 RuntimeError"""
    _patch_httpx(monkeypatch, [_FakeResponse({"code": 1001, "message": "额度已用尽"})])
    with pytest.raises(RuntimeError, match="额度已用尽"):
        OXROnline({}).parse_document(b"%PDF", "a.pdf")


# ==================== OcrService 多配置降级链 ====================
class _FlakyOcrEngine:
    """首个引擎: 模拟额度耗尽/限流失败"""

    def recognize(self, image_cv):
        raise RuntimeError("免费额度已用尽")

    def parse_document(self, data, filename):
        raise RuntimeError("免费额度已用尽")


class _GoodOcrEngine:
    """备用引擎: 返回成功结果"""

    def recognize(self, image_cv):
        return {"ts": {"total": 0.1}, "results": [{"box": [[0, 0]], "text": "备用结果", "score": 1.0}], "engine": "oxr"}

    def parse_document(self, data, filename):
        return "备用文档文本"


class _StubEntry:
    """ModelEntryService 桩: 按候选顺序返回预设引擎"""

    def __init__(self, engines):
        self._engines = list(engines)

    async def list_candidate_configs(self, model_type, *, user_id=None):
        return [SimpleNamespace(id=str(i)) for i in range(len(self._engines))]

    async def get_engine(self, model_type, *, model_id=None, **kwargs):
        return self._engines[int(model_id)]


def test_ocr_service_recognize_fallback_chain():
    """OCR 图片识别: 首条配置失败时自动切换下一条"""
    result = asyncio.run(
        OcrService(_StubEntry([_FlakyOcrEngine(), _GoodOcrEngine()])).recognize(
            np.zeros((4, 4, 3), dtype="uint8")
        )
    )
    assert result["engine"] == "oxr"
    assert result["results"][0]["text"] == "备用结果"
    assert result["results"][0]["index"] == 0


def test_ocr_service_document_fallback_chain():
    """OCR 文档解析: 首条配置失败时自动切换下一条"""
    result = asyncio.run(
        OcrService(_StubEntry([_FlakyOcrEngine(), _GoodOcrEngine()])).recognize_document(
            b"%PDF", "a.pdf"
        )
    )
    assert result.text == "备用文档文本"
    assert result.engine == "_GoodOcrEngine"
