# -*- coding: utf-8 -*-
"""module_ai 语音在线方案(能力全部外部服务接入)标准测试

覆盖:
- OnlineASR: extra.protocol 分派(dashscope/openai 兼容), 伪流式会话切片与合并
- OnlineTTS: openai 兼容整段合成后切片异步产出, _slice_pcm 空音频契约
- VoiceService 门面: 统一入口 ModelEntryService 的配置解析/显式方案匹配/缓存失效/
  存量旧值配置构建, tts_stream_async 真异步与同步切片回退的路径选择
- ensure_voice_server_type 迁移钩子: dashscope 归一化 online + 本地方案批量停用(幂等)

说明: 本地推理(sherpa/qwen)与 vad/denoise 前置管线已全部下线, 不再覆盖。
"""

import json
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

import module_ai.config.server as ai_server_mod
from module_ai.do.voice import VoiceEngine
from module_ai.service.model_config import ModelEntryService, ModelNotConfiguredError
from module_ai.service.voice import VoiceService
from module_ai.utils.voice.asr.dashscope import DashscopeASR
from module_ai.utils.voice.asr.online import OnlineASR, PseudoStreamSession, _is_realtime_model
from module_ai.utils.voice.audio import load_audio, pcm_to_wav_bytes, to_pcm16
from module_ai.utils.voice.interface import TTSEngine
from module_ai.utils.voice.tts.online import OnlineTTS, _slice_pcm


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

    def post(self, url: str, headers: dict | None = None, json: dict | None = None,
             files: dict | None = None, data: dict | None = None, **kw):
        self.calls.append({"method": "post", "url": url, "headers": headers,
                           "json": json, "files": files, "data": data})
        return self.responses.pop(0)


def _patch_httpx(monkeypatch, responses: list[_FakeResponse]) -> None:
    """全局替换 httpx.Client 为打桩工厂(测试结束自动还原)"""
    monkeypatch.setattr(httpx, "Client", lambda **kw: _FakeHttpClient(responses, **kw))


# ==================== 模型配置/DAO 桩 ====================
class _StubDao:
    """模型配置 DAO 桩: 按类型返回预设配置, 不访问数据库(供统一入口解析配置)"""

    def __init__(self, configs: dict[str, "_FakeConfig | None"]):
        self._configs = configs

    async def get_first_by_type(self, model_type: str, session=None, server_type: str | None = None):
        config = self._configs.get(model_type)
        if config is None:
            return None
        if server_type and str(config.server_type) != server_type:
            return None
        return config


class _FakeConfig:
    """model_config 表记录桩(仅包含配置解析/引擎构建所需字段)"""

    def __init__(self, server_type, model: str = "qwen3-asr-flash",
                 extra: dict | None = None, cfg_id: str = "cfg_1",
                 updated_at: str = "2026-01-01T00:00:00",
                 api_key: str = "", url: str | None = None, timeout: int = 60,
                 model_type: str = "asr"):
        self.id = cfg_id
        self.updated_at = updated_at
        self.model_type = model_type
        self.server_type = server_type
        self.model = model
        self.extra = extra or {}
        # 顶层字段回填所需(service.model_config.flatten_conf 读取)
        self.api_key = api_key
        self.url = url
        self.timeout = timeout


def _make_service(configs: dict[str, "_FakeConfig | None"]) -> VoiceService:
    """构造走桩 DAO 的 VoiceService(解析/构建/缓存由统一入口 ModelEntryService 承担)"""
    return VoiceService(model_entry=ModelEntryService(model_config_dao=_StubDao(configs)))


# ==================== OnlineASR: 协议分派与伪流式 ====================
def test_is_realtime_model():
    """实时系列按前缀匹配: paraformer-realtime-v2 命中 paraformer-realtime"""
    realtime = ["paraformer-realtime", "gummy"]
    assert _is_realtime_model("paraformer-realtime-v2", realtime)
    assert _is_realtime_model("gummy-chat-v1", realtime)
    assert not _is_realtime_model("qwen3-asr-flash", realtime)
    assert not _is_realtime_model("", realtime)


def test_online_asr_protocol_dispatch():
    """OnlineASR 按 extra.protocol 分派: 缺省 dashscope, openai 走兼容实现"""
    assert isinstance(OnlineASR({})._sync_engine, DashscopeASR)
    assert isinstance(OnlineASR({"protocol": "dashscope"})._sync_engine, DashscopeASR)
    # openai 协议应为兼容实现类(非 DashscopeASR)
    openai_engine = OnlineASR({"protocol": "openai", "api_key": "sk-test"})._sync_engine
    assert not isinstance(openai_engine, DashscopeASR)
    assert type(openai_engine).__name__ == "_OpenAICompatibleASR"


def test_online_asr_openai_recognize(monkeypatch):
    """OnlineASR openai 协议: multipart 上传音频, 返回 text 字段"""
    _patch_httpx(monkeypatch, [_FakeResponse({"text": " 你好世界 "})])
    engine = OnlineASR({"protocol": "openai", "api_key": "sk-test",
                        "url": "http://vllm.local/v1/audio/transcriptions",
                        "model": "qwen3-asr-flash"})
    text = engine.recognize(b"RIFF0000WAVE", sample_rate=16000)
    assert text == "你好世界"

    call = _FakeHttpClient.last.calls[0]
    assert call["url"] == "http://vllm.local/v1/audio/transcriptions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["data"] == {"model": "qwen3-asr-flash"}
    assert call["files"]["file"][0] == "audio.wav"


def test_online_asr_openai_missing_api_key():
    """openai 协议缺少 api_key 应给出可操作的错误提示(不发网络请求)"""
    engine = OnlineASR({"protocol": "openai"})
    with pytest.raises(RuntimeError, match="api_key"):
        engine.recognize(b"RIFF0000WAVE")


def test_pseudo_stream_session_chunk_and_order():
    """伪流式: 缓冲达阈值提交切片, flush 等待尾段, 按提交顺序拼接文本"""
    counter = {"n": 0}

    class _StubRecognizer:
        def recognize(self, wav: bytes, sample_rate: int = 16000) -> str:
            counter["n"] += 1
            return f"C{counter['n'] - 1}"

    # 0.5s 切片(16000Hz int16 -> 16000 字节): 总量 20000 字节 -> 16000 + 4000 两个切片
    session = PseudoStreamSession(_StubRecognizer(), sample_rate=16000, chunk_seconds=0.5)
    session.accept(b"\x00\x00" * 6000)  # 12000 字节, 未达阈值
    session.accept(b"\x00\x00" * 4000)  # 累计 20000, 触发切片1(16000)
    # 非阻塞收割: 切片完成与否不影响调用(桩太快可能已收到 C0)
    assert session.result() in ("", "C0")
    session.flush()  # 提交尾段并等待全部完成
    assert session.result() == "C0C1"
    session.destroy()


async def test_online_asr_pseudo_stream_async_path():
    """非实时模型(如 qwen3-asr-flash)应走伪流式会话而非真 WS"""
    engine = OnlineASR({"protocol": "dashscope", "model": "qwen3-asr-flash"})
    stream = await engine.create_stream_async()
    assert isinstance(stream, PseudoStreamSession)
    await engine.stream_accept_async(stream, b"\x00\x00" * 100)
    assert await engine.stream_result_async(stream) == ""
    await engine.stream_destroy_async(stream)  # flush + destroy, 不应抛异常


# ==================== OnlineTTS: openai 兼容回退与切片 ====================
def _make_wav(sample_rate: int = 22050, seconds: float = 0.5) -> bytes:
    """构造真实 WAV 字节(正弦波, 供打桩响应/解码验证)"""
    n = int(sample_rate * seconds)
    samples = (np.sin(np.linspace(0, 440 * 2 * np.pi, n)) * 0.5).astype("float32")
    return pcm_to_wav_bytes(to_pcm16(samples), sample_rate)


async def test_online_tts_openai_async_stream(monkeypatch):
    """openai 协议无真流式: 线程池整段合成后按 200ms 切片异步产出"""
    wav = _make_wav(22050, 0.5)
    _patch_httpx(monkeypatch, [_FakeResponse(content=wav)])
    engine = OnlineTTS({"protocol": "openai", "api_key": "sk-test",
                        "url": "http://vllm.local/v1/audio/speech", "model": "qwen3-tts-flash"})

    chunks: list[tuple[bytes, int, bool]] = []
    async for chunk, sr, is_final in engine.synthesize_stream_async("你好", sample_rate=22050):
        chunks.append((chunk, sr, is_final))

    assert _FakeHttpClient.last.calls[0]["json"]["model"] == "qwen3-tts-flash"
    assert len(chunks) >= 2, "0.5s 音频应切成多片"
    assert chunks[-1][2] is True, "最后一片应标记 is_final"
    assert all(sr == 22050 for _, sr, _ in chunks)
    total_pcm = b"".join(c for c, _, _ in chunks)
    samples, out_sr = load_audio(pcm_to_wav_bytes(total_pcm, 22050))
    assert out_sr == 22050 and len(samples) > 0


def test_slice_pcm_empty():
    """空 PCM 应产出单个空片并直接标记 is_final"""
    out = list(_slice_pcm(b"", 22050))
    assert out == [(b"", 22050, True)]


# ==================== VoiceService: 统一入口配置驱动解析 ====================
async def test_voice_service_resolve_online():
    """asr 配置 server_type=online 应构建 OnlineASR 并展平 extra"""
    service = _make_service({
        "asr": _FakeConfig("online", model="qwen3-asr-flash",
                           extra={"protocol": "dashscope", "language": "zh"}),
    })
    engine = await service.get_asr()
    assert isinstance(engine, OnlineASR)
    assert engine._conf["model"] == "qwen3-asr-flash"
    assert engine._conf["language"] == "zh"


async def test_voice_service_explicit_online():
    """显式指定 online 方案: 按类型+方案精确匹配配置; 未配置时给出可操作报错"""
    service = _make_service({"asr": _FakeConfig("online")})
    engine = await service.get_asr(VoiceEngine.ONLINE)
    assert isinstance(engine, OnlineASR)

    empty = _make_service({})
    with pytest.raises(ModelNotConfiguredError, match="online"):
        await empty.get_asr(VoiceEngine.ONLINE)


async def test_voice_service_cache_invalidated_by_updated_at():
    """引擎缓存按配置 updated_at 失效: 配置变更后重建实例"""
    config = _FakeConfig("online", extra={"protocol": "dashscope"}, model_type="tts")
    service = _make_service({"tts": config})
    first = await service.get_tts()
    again = await service.get_tts()
    assert first is again, "同配置应命中缓存"
    config.updated_at = "2026-02-02T00:00:00"
    rebuilt = await service.get_tts()
    assert rebuilt is not first, "配置变更后应重建引擎"


async def test_voice_service_legacy_server_type_builds_online():
    """存量旧值 server_type=dashscope(未迁移) 配置仍可解析, 构建为 OnlineASR(本地方案已下线)"""
    service = _make_service({"asr": _FakeConfig("dashscope")})
    engine = await service.get_asr()
    assert isinstance(engine, OnlineASR)


# ==================== tts_stream_async 路径选择 ====================
class _SyncOnlyTTS(TTSEngine):
    """仅实现同步合成的 TTS 桩(未覆写 synthesize_stream_async, 供回退路径验证)"""

    def synthesize(self, text: str, speaker: int = 0, speed: float = 1.0,
                   sample_rate: int = 22050) -> tuple[bytes, int]:
        return b"\x00\x00" * 2205, sample_rate


async def test_tts_stream_async_falls_back_sync():
    """未覆写真异步流式的引擎: tts_stream_async 应回退同步切片路径(is_async=False)"""
    service = _make_service({})

    async def _fake_get_tts(engine=None, user_id=None):
        return _SyncOnlyTTS()

    service.get_tts = _fake_get_tts  # type: ignore[method-assign]
    iterator, effective, is_async = await service.tts_stream_async("你好")
    assert effective is VoiceEngine.ONLINE
    assert is_async is False
    assert not hasattr(iterator, "__anext__"), "回退路径应为同步迭代器"


async def test_tts_stream_async_online_uses_async(monkeypatch):
    """OnlineTTS(openai 协议) 覆写了真异步流式: 应走异步路径(is_async=True)"""
    wav = _make_wav(22050, 0.4)
    _patch_httpx(monkeypatch, [_FakeResponse(content=wav)])
    service = _make_service({
        "tts": _FakeConfig("online", model="qwen3-tts-flash",
                           extra={"protocol": "openai", "api_key": "sk-test"}, model_type="tts"),
    })
    iterator, effective, is_async = await service.tts_stream_async("你好", sample_rate=22050)
    assert effective is VoiceEngine.ONLINE
    assert is_async is True
    chunks = [chunk async for chunk, _sr, _final in iterator]
    assert len(chunks) >= 1, "异步流式应产出至少一片音频"


# ==================== ensure_voice_server_type 迁移钩子 ====================
class _FakeResult:
    """SQL 执行结果桩: fetchall 返回预置行, rowcount 可预设"""

    def __init__(self, rows: list[tuple], rowcount: int = 0):
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConn:
    """连接桩: SELECT 返回预置行, 带参 UPDATE 记录参数, 全部语句记录 SQL 文本"""

    def __init__(self, rows: list[tuple]):
        self._rows = rows
        self.updates: list[dict] = []
        self.statements: list[str] = []

    async def execute(self, stmt, params: dict | None = None):
        sql = str(stmt)
        self.statements.append(sql)
        if params is not None:
            self.updates.append(params)
            return _FakeResult([], rowcount=1)
        if "SELECT" in sql.upper():
            return _FakeResult(self._rows)
        return _FakeResult([], rowcount=0)


class _FakeEngine:
    """引擎桩: begin() 返回异步上下文, 交付预置连接"""

    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def begin(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *args):
                return False

        return _Ctx()


async def test_ensure_voice_server_type_migrates(monkeypatch):
    """dashscope(asr/tts) 应归一化为 online, 原值写入 extra.legacy_server_type;
    本地方案(sherpa/qwen/local)与 vad/denoise 改为批量停用而非改写 server_type"""
    conn = _FakeConn([
        ("cfg-1", "dashscope", {"voice": "longxiaochun"}),
        ("cfg-2", "dashscope", '{"model": "qwen3-asr-flash"}'),  # str 形态 extra(防归一)
    ])
    fake_db = SimpleNamespace(db_rel=SimpleNamespace(engine=_FakeEngine(conn)))
    monkeypatch.setattr(ai_server_mod, "db_manager", fake_db)

    await ai_server_mod.ensure_voice_server_type()

    assert len(conn.updates) == 2
    by_id = {u["id"]: u for u in conn.updates}
    # dashscope -> online, extra dict 保留原键 + legacy 标记
    assert json.loads(by_id["cfg-1"]["extra"]) == {"voice": "longxiaochun", "legacy_server_type": "dashscope"}
    # str extra 解析后保留 model 键
    assert json.loads(by_id["cfg-2"]["extra"]) == {"model": "qwen3-asr-flash", "legacy_server_type": "dashscope"}
    # 批量停用语句覆盖全部已下线方案
    bulk = [s for s in conn.statements if "is_active = FALSE" in s]
    assert bulk, "应存在批量停用语句"
    assert all(key in bulk[0] for key in ("sherpa", "qwen", "local", "vad", "denoise"))


async def test_ensure_voice_server_type_noop(monkeypatch):
    """无存量旧值/未初始化 DB 时应直接返回, 不产生任何更新"""
    # 情形1: db_rel 未初始化
    monkeypatch.setattr(ai_server_mod, "db_manager", SimpleNamespace(db_rel=None))
    await ai_server_mod.ensure_voice_server_type()  # 不应抛异常

    # 情形2: 查询无结果
    conn = _FakeConn([])
    monkeypatch.setattr(
        ai_server_mod, "db_manager",
        SimpleNamespace(db_rel=SimpleNamespace(engine=_FakeEngine(conn))),
    )
    await ai_server_mod.ensure_voice_server_type()
    assert conn.updates == [], "无旧值时不应执行带参 UPDATE"


def test_voice_engine_enum_values():
    """VoiceEngine 仅含 online 单值(历史值由 resolve_engine 归一化)"""
    assert {e.value for e in VoiceEngine} == {"online"}
