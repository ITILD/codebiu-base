# -*- coding: utf-8 -*-
"""module_ai 生图引擎(OpenAI 兼容 /images/generations)标准测试

覆盖:
- 类型映射: server_types_for("image") 仅 openai/dashscope; 能力清单含文生图/图生图
- 统一入口: build_image_model 按 server_type 分派, 不支持的方案抛 ValueError
- 引擎: 请求体默认参数合并与显式覆盖、结果解析(url/b64_json)、错误状态码抛错
- 路由: /ai/llm/image、/ai/llm/test-image、/ai/llm/rerank 已注册

说明: aiohttp.ClientSession 全局打桩, 零外部依赖, 不发起真实生图请求。
"""

import json

import aiohttp
import pytest

from module_ai.do.llm import MODEL_CAPABILITIES
from module_ai.utils.llm.factory.builder import build_image_model
from module_ai.utils.llm.image.impl.openai import OpenAIImage
from module_ai.utils.llm.types import ModelServerType, ModelType, server_types_for


def _config(**kwargs):
    """构造生图模型配置(默认 openai 兼容 + qwen-image-3.0)"""
    from module_ai.do.model_config import ModelConfig

    data = {
        "user_id": "test-user",
        "model_type": ModelType.IMAGE,
        "server_type": ModelServerType.OPENAI,
        "model": "qwen-image-3.0",
        "api_key": "test-key-not-real",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    data.update(kwargs)
    return ModelConfig(**data)


# ==================== aiohttp 打桩(零外部依赖) ====================
class _FakeAioResponse:
    """aiohttp 响应桩: 预设状态码与文本内容"""

    def __init__(self, body: str, status: int = 200):
        self._body = body
        self.status = status

    async def text(self) -> str:
        return self._body


class _FakePostContext:
    """session.post(...) 异步上下文桩"""

    def __init__(self, response: _FakeAioResponse):
        self._response = response

    async def __aenter__(self) -> _FakeAioResponse:
        return self._response

    async def __aexit__(self, *args) -> bool:
        return False


class _FakeSession:
    """aiohttp.ClientSession 桩: 记录请求并按预设响应返回"""

    last: "_FakeSession | None" = None

    def __init__(self, response: _FakeAioResponse, **kwargs):
        self.response = response
        self.calls: list[dict] = []
        type(self).last = self

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    def post(self, url: str, headers: dict | None = None, json: dict | None = None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakePostContext(self.response)


def _patch_aiohttp(monkeypatch, response: _FakeAioResponse) -> None:
    """替换 aiohttp.ClientSession 为打桩工厂(测试结束自动还原)"""
    monkeypatch.setattr(
        aiohttp, "ClientSession", lambda **kw: _FakeSession(response, **kw)
    )


# ==================== 类型映射与统一入口 ====================
def test_server_types_for_image():
    """生图仅支持 openai(兼容协议)与 dashscope(百炼兼容模式, 同协议)"""
    assert server_types_for(ModelType.IMAGE) == [
        ModelServerType.OPENAI,
        ModelServerType.DASHSCOPE,
    ]
    assert server_types_for("image") == [
        ModelServerType.OPENAI,
        ModelServerType.DASHSCOPE,
    ]


def test_model_capabilities_image():
    """生图能力清单包含文生图与图生图两项"""
    assert MODEL_CAPABILITIES[ModelType.IMAGE.value] == [
        ("image", "文生图"),
        ("image_edit", "图生图"),
    ]


def test_build_image_model_dispatch():
    """openai/dashscope 均构建 OpenAI 兼容引擎; 其他方案抛 ValueError"""
    for server_type in (ModelServerType.OPENAI, ModelServerType.DASHSCOPE):
        engine = build_image_model(_config(server_type=server_type))
        assert isinstance(engine, OpenAIImage)
        assert engine.model == "qwen-image-3.0"
        assert engine.endpoint.endswith("/images/generations")

    with pytest.raises(ValueError, match="暂不支持图像生成"):
        build_image_model(_config(server_type=ModelServerType.OLLAMA))


def test_build_image_model_extra_defaults():
    """extra 中的默认参数注入引擎, 超时优先取 extra.timeout"""
    engine = build_image_model(
        _config(
            timeout=60,
            extra={"size": "1280x1280", "n": 2, "prompt_extend": True, "timeout": 300},
        )
    )
    assert engine.defaults == {"size": "1280x1280", "n": 2, "prompt_extend": True}
    assert engine.timeout == 300


# ==================== 请求体构建与结果解析 ====================
def test_build_payload_defaults_and_override():
    """默认参数生效; 显式入参优先; 空值不下发"""
    engine = OpenAIImage(
        api_key="test-key",
        model="qwen-image-3.0",
        defaults={"size": "1024*1024", "n": 2, "watermark": False},
    )
    # 仅提示词: 使用配置默认值
    payload = engine._build_payload("一只猫")
    assert payload == {
        "model": "qwen-image-3.0",
        "prompt": "一只猫",
        "size": "1024x1024",
        "n": 2,
        "watermark": False,
    }
    # 显式覆盖: size(兼容 * 分隔)/n/参考图
    payload = engine._build_payload(
        "改成蓝色", image="data:image/png;base64,xxx", size="512*512", n=1
    )
    assert payload["image"] == "data:image/png;base64,xxx"
    assert payload["size"] == "512x512"
    assert payload["n"] == 1


def test_parse_result_url_and_b64():
    """优先取 url; 无 url 时兼容 b64_json 转 data URL; 空项丢弃"""
    results = OpenAIImage._parse_result(
        {
            "data": [
                {"url": "https://example.com/a.png", "revised_prompt": "改写后"},
                {"b64_json": "AAAA"},
                {"url": ""},
            ]
        }
    )
    assert results == [
        {"url": "https://example.com/a.png", "revised_prompt": "改写后"},
        {"url": "data:image/png;base64,AAAA", "revised_prompt": ""},
    ]


# ==================== 真实调用链路(打桩) ====================
async def test_agenerate_success(monkeypatch):
    """成功响应: 请求体含提示词与默认参数, 返回图片列表"""
    body = json.dumps({"data": [{"url": "https://example.com/a.png"}]})
    _patch_aiohttp(monkeypatch, _FakeAioResponse(body))
    engine = OpenAIImage(
        api_key="test-key",
        model="qwen-image-3.0",
        defaults={"size": "1024*1024"},
    )

    results = await engine.agenerate("一只戴墨镜的橘猫")

    assert results == [{"url": "https://example.com/a.png", "revised_prompt": ""}]
    call = _FakeSession.last.calls[0]
    assert call["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["json"] == {
        "model": "qwen-image-3.0",
        "prompt": "一只戴墨镜的橘猫",
        "size": "1024x1024",
        "n": 1,
    }


async def test_agenerate_error_status(monkeypatch):
    """非 2xx 状态码: 抛出 RuntimeError 并带响应体摘要"""
    _patch_aiohttp(monkeypatch, _FakeAioResponse('{"message": "invalid api key"}', 401))
    engine = OpenAIImage(api_key="bad-key", model="qwen-image-3.0")

    with pytest.raises(RuntimeError, match="401"):
        await engine.agenerate("一只猫")


async def test_agenerate_empty_result(monkeypatch):
    """响应无图片: 抛出 RuntimeError"""
    _patch_aiohttp(monkeypatch, _FakeAioResponse(json.dumps({"data": []})))
    engine = OpenAIImage(api_key="test-key", model="qwen-image-3.0")

    with pytest.raises(RuntimeError, match="结果为空"):
        await engine.agenerate("一只猫")


# ==================== 输入限制(参考图压缩 / token 度量) ====================
def _noise_png(size: int = 900) -> bytes:
    """生成指定边长的高熵 PNG(体积大, 用于触发压缩)"""
    import os as _os
    from io import BytesIO

    from PIL import Image

    img = Image.frombytes("RGB", (size, size), _os.urandom(size * size * 3))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_compress_reference_image_reduces_size():
    """超限参考图自动缩放/转 JPEG, 压缩后体积达标并返回可用 data URL"""
    import base64

    from module_ai.utils.llm.limits import compress_reference_image

    raw = _noise_png()
    max_bytes = 200 * 1024
    assert len(raw) > max_bytes
    source = "data:image/png;base64," + base64.b64encode(raw).decode()

    compressed, meta = compress_reference_image(source, max_bytes=max_bytes)

    assert compressed.startswith("data:image/jpeg;base64,")
    assert meta["compressed"] is True
    assert meta["original_bytes"] == len(raw)
    assert meta["bytes"] <= max_bytes
    # 压缩结果可再次解码为图片
    from io import BytesIO

    from PIL import Image

    Image.open(BytesIO(base64.b64decode(compressed.split(",", 1)[1]))).verify()


def test_compress_reference_image_keeps_small_and_remote():
    """未超限参考图原样保留; http 地址不本地处理"""
    import base64

    from module_ai.utils.llm.limits import compress_reference_image

    small = "data:image/png;base64," + base64.b64encode(_noise_png(32)).decode()
    kept, meta = compress_reference_image(small)
    assert kept == small and meta["compressed"] is False

    url = "https://example.com/a.png"
    kept, meta = compress_reference_image(url)
    assert kept == url and meta["bytes"] == 0


def test_prepare_reference_image_limit_and_friendly_error():
    """服务层参考图治理返回 bytes 度量; 远端 10MB 错误转可执行提示"""
    import base64

    from module_ai.service.llm import LLMService
    from module_ai.utils.llm.limits import MAX_IMAGE_BYTES, friendly_remote_error

    raw = _noise_png(32)
    reference, info = LLMService._prepare_reference_image(
        "data:image/png;base64," + base64.b64encode(raw).decode()
    )
    assert reference and info is not None
    assert info.unit == "bytes" and info.limit == MAX_IMAGE_BYTES
    assert info.used == len(raw)

    with pytest.raises(Exception):
        LLMService._prepare_reference_image("data:image/png;base64,not-base64!!")

    msg = friendly_remote_error(
        '{"error":{"message":"File size exceeds maximum allowed size of 10485760 bytes"}}'
    )
    assert "10MB" in msg


def test_limit_info_and_token_count():
    """统一度量口径与 token 计数(中文按字近似)"""
    from module_ai.utils.llm.limits import count_tokens, limit_info

    assert count_tokens("机器学习") > 0
    assert limit_info(11, 10) == {
        "used": 11,
        "limit": 10,
        "unit": "token",
        "exceeded": True,
    }
    assert limit_info(0, 0)["exceeded"] is False


# ==================== 路由注册 ====================
async def test_image_routes_registered(anon_client):
    """llm 子应用已注册生图/生图测试/重排路由"""
    resp = await anon_client.get("/ai/openapi.json")
    assert resp.status_code == 200, resp.text
    # 子应用 openapi 不携带挂载前缀 /ai
    paths = set(resp.json()["paths"].keys())
    for path in ("/llm/image", "/llm/test-image", "/llm/rerank"):
        assert path in paths, f"路由未注册: {path}"
    # 旧 rerank 独立控制器已合并进 llm, 不应再暴露 /rerank 根路由
    assert "/rerank" not in paths
