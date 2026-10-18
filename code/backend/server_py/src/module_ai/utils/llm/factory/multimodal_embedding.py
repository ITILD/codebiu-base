"""阿里云百炼多模态向量化客户端(tongyi-embedding-vision 系专用)

tongyi-embedding-vision 系模型不支持 OpenAI 兼容 /embeddings 端点,
须调用百炼原生多模态向量化接口:
    POST {origin}/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding
    input.contents: [{text|image}, ...] 批量提交, parameters.dimension 指定维度

实现 LangChain Embeddings 接口, 可无缝替换 OpenAIEmbeddings。
"""
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings

# 原生多模态向量化接口路径
_NATIVE_PATH = "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"

# 服务端支持的向量维度档位
_ALLOWED_DIMENSIONS = (64, 128, 256, 512, 768)

# 单次请求最大内容条数(服务端限制)
_MAX_BATCH = 10

# 默认请求超时(秒)
_DEFAULT_TIMEOUT = 60


def _nearest_dimension(dimensions: int | None) -> int | None:
    """将请求维度映射到服务端支持的最近档位(不在档位内时)"""
    if dimensions is None or dimensions in _ALLOWED_DIMENSIONS:
        return dimensions
    return min(_ALLOWED_DIMENSIONS, key=lambda d: abs(d - dimensions))


class DashscopeMultimodalEmbeddings(Embeddings):
    """百炼原生多模态向量化模型客户端(tongyi-embedding-vision 系)"""

    def __init__(self, model: str, api_key: str, base_url: str, dimensions: int | None = None, timeout: float = _DEFAULT_TIMEOUT):
        """
        :param model: 模型名(如 tongyi-embedding-vision-flash)
        :param api_key: 百炼 API Key
        :param base_url: 兼容模式地址(如 https://dashscope.aliyuncs.com/compatible-mode/v1),
                         自动推导原生端点; 已含原生路径则原样使用
        :param dimensions: 向量维度(自动映射到最近支持档位)
        :param timeout: 请求超时秒数
        """
        self._model = model
        self._api_key = api_key
        base = (base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
        self._url = base if base.endswith(_NATIVE_PATH) else f"{base.split('/compatible-mode')[0]}{_NATIVE_PATH}"
        self._dimensions = _nearest_dimension(dimensions)
        self._timeout = timeout

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """一批文本提交原生接口, 按返回 index 还原顺序"""
        payload: dict[str, Any] = {"model": self._model, "input": {"contents": [{"text": t} for t in texts]}}
        if self._dimensions is not None:
            payload["parameters"] = {"dimension": self._dimensions}
        try:
            resp = httpx.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as e:
            raise RuntimeError(f"多模态向量化请求失败: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(f"多模态向量化请求失败({resp.status_code}): {resp.text[:500]}")
        embeddings = ((resp.json() or {}).get("output") or {}).get("embeddings") or []
        if len(embeddings) != len(texts):
            raise RuntimeError(f"多模态向量化返回数量不符: 期望 {len(texts)}, 实际 {len(embeddings)}")
        ordered = sorted(embeddings, key=lambda e: int(e.get("index") or 0))
        return [list(e.get("embedding") or []) for e in ordered]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化(自动分批, 顺序与输入一致)"""
        results: list[list[float]] = []
        for i in range(0, len(texts), _MAX_BATCH):
            results.extend(self._embed_batch(texts[i : i + _MAX_BATCH]))
        return results

    def embed_query(self, text: str) -> list[float]:
        """单条文本向量化"""
        return self._embed_batch([text])[0]
