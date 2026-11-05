"""OXR(Optical Everything Recognition) 官方在线解析引擎实现(server_type=online)

OXR 1.0 是 SoMark 开源的文档解析模型, 官方提供免注册免费额度接口:
    POST {base}/parse/sync (multipart: file + api_key + output_formats)
    同步返回 markdown/json, 无需轮询

免费额度限制(官方): 单文件 10MB / 20 页; 超出请拆分后再提交。
``api_key`` 免费接口填 ``dummy`` 即可, 付费/自部署服务按其要求填写。

引擎配置来源: model_config 表(model_type=ocr)的 url/api_key/timeout:
    - url: 默认 https://free-oxr.somark.cn/api/v1(可填完整 /parse/sync 地址)
    - api_key: 默认 dummy(免费接口无需真实 Key)
    - timeout: 单次请求超时秒数(默认 120, 大文档可调高)

结果结构与本地 paddle 流水线对齐: {"ts": {...}, "results": [{box, text, score}]}
"""
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# OXR 官方免费接口地址(免费额度无需注册/Key)
_DEFAULT_BASE_URL = "https://free-oxr.somark.cn/api/v1"

# 免费接口默认 api_key(官方约定可用任意占位值, 统一用 dummy)
_DEFAULT_API_KEY = "dummy"

# 单次 HTTP 请求默认超时(秒)
_DEFAULT_TIMEOUT = 120

# 文档解析支持的 MIME 映射(其余按二进制流提交, 由服务端判定)
_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class OXROnline:
    """OXR 1.0 官方在线解析引擎(整文件同步解析, 输出 markdown)"""

    def __init__(self, conf: dict | None = None):
        """
        :param conf: 动态配置(model_config 映射), 可含:
            - url: OXR 服务地址(默认官方免费地址)
            - api_key: 访问密钥(默认 dummy)
            - timeout: 单次请求超时秒数(默认 120)
        """
        self._conf = conf or {}

    @property
    def _api_key(self) -> str:
        """免费接口无需真实 Key, 缺省用 dummy; 自部署服务可填真实值"""
        return str(self._conf.get("api_key") or "").strip() or _DEFAULT_API_KEY

    def _endpoint(self) -> str:
        """解析端点: 支持配置 base 地址或完整 /parse/sync 地址"""
        url = str(self._conf.get("url") or _DEFAULT_BASE_URL).strip().rstrip("/")
        return url if url.endswith("/parse/sync") else f"{url}/parse/sync"

    @staticmethod
    def _extract_text(payload: dict) -> str:
        """从同步响应抽取文本: 优先 outputs.markdown, 回退 json.pages 的块内容"""
        code = payload.get("code")
        if code not in (None, 0):
            raise RuntimeError(
                f"OXR 解析失败: {payload.get('message') or payload.get('error') or code}"
            )
        data = payload.get("data") or {}
        outputs = ((data.get("result") or {}).get("outputs")) or {}
        markdown = outputs.get("markdown")
        if isinstance(markdown, str) and markdown.strip():
            return markdown.strip()
        # 兼容部分版本把 markdown 放在 result 顶层
        result = data.get("result") or {}
        for key in ("markdown", "text"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        # 回退: json 输出按页/块拼接
        pages = ((outputs.get("json") or {}).get("pages")) or []
        texts: list[str] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_md = page.get("markdown")
            if isinstance(page_md, str) and page_md.strip():
                texts.append(page_md.strip())
                continue
            for block in page.get("blocks") or page.get("elements") or []:
                if not isinstance(block, dict):
                    continue
                content = block.get("content") or block.get("text")
                if isinstance(content, str) and content.strip():
                    texts.append(content.strip())
        return "\n".join(texts)

    def _parse_sync(self, data: bytes, filename: str, mime: str) -> str:
        """上传文件到 /parse/sync 并返回 markdown 文本"""
        try:
            import httpx

            with httpx.Client(
                timeout=float(self._conf.get("timeout") or _DEFAULT_TIMEOUT)
            ) as client:
                resp = client.post(
                    self._endpoint(),
                    # dict 值传列表 → httpx 按同名字段重复编码(与官方 multipart 约定一致)
                    data={
                        "api_key": self._api_key,
                        "output_formats": ["markdown"],
                    },
                    files={"file": (filename or "document.bin", data, mime)},
                )
        except Exception as e:
            raise RuntimeError(f"OXR 解析请求失败: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(f"OXR 解析请求失败({resp.status_code}): {resp.text[:500]}")
        text = self._extract_text(resp.json())
        if not text:
            raise RuntimeError("OXR 未返回解析文本")
        return text

    def recognize(self, image_cv) -> dict:
        """上传图片识别文字, 返回与本地流水线同构的结果

        :param image_cv: cv2 图像(numpy.ndarray)
        :return: {"ts": {"total": 秒}, "results": [{"box", "text", "score"}], "engine": "oxr"}
        """
        import cv2
        import numpy as np

        if not isinstance(image_cv, np.ndarray):
            raise RuntimeError("OXR 仅支持 cv2 图像输入")
        h, w = image_cv.shape[:2]
        ok, buf = cv2.imencode(".png", image_cv)
        if not ok:
            raise RuntimeError("图片编码失败, 无法上传 OXR")
        start = time.time()
        text = self._parse_sync(buf.tobytes(), "image.png", "image/png")
        return {
            "ts": {"total": round(time.time() - start, 3)},
            "results": [{"box": [[0, 0], [w, 0], [w, h], [0, h]], "text": text, "score": 1.0}],
            "engine": "oxr",
        }

    def parse_document(self, data: bytes, filename: str) -> str:
        """整份文档解析(pdf/图片): 同步上传并返回 markdown 文本

        :param data: 文件原始字节(pdf/png/jpg)
        :param filename: 文件名(用于推断 MIME)
        :return: markdown 文本
        """
        suffix = Path(filename or "").suffix.lower()
        mime = _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
        return self._parse_sync(data, filename, mime)
