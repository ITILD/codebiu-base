"""PaddleOCR 官方云 API 在线 OCR 引擎实现(server_type=online)

对接 PaddleOCR 官方托管服务(paddleocr.aistudio-app.com 异步 jobs 协议),
适用于 PaddleOCR-VL 系文档解析模型与 PP-OCR 系 OCR 模型:

    1. POST {url} (multipart: model + optionalPayload + file) 创建任务
    2. GET  {url}/{jobId} 轮询状态(pending/running/done/failed)
    3. 下载 resultUrl.jsonUrl 指向的 JSONL, 抽取整图纯文本

引擎配置来源: model_config 表(model_type=ocr, server_type=online)的
model/url/api_key 字段(与 DashscopeOCR 同构)。

结果结构与本地 paddle 流水线对齐: {"ts": {...}, "results": [{box, text, score}]}
在线结果 box 为整图矩形坐标列表(score 恒为 1.0), 不参与分段/版面分析。
"""
import base64
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认 jobs 端点(OCR/文档解析任务共用)
_DEFAULT_JOBS_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"

# 单次 HTTP 请求默认超时(秒)
_DEFAULT_TIMEOUT = 60
# 轮询总预算(秒): 长文档解析可能超过单请求 timeout, 取较大值兜底
_DEFAULT_POLL_BUDGET = 300
# 轮询间隔(秒)
_POLL_INTERVAL = 2.0

# 文档解析支持的 MIME 映射(其余按二进制流提交, 由服务端判定)
_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class PaddleOCROnline:
    """PaddleOCR 官方云 API 引擎(PaddleOCR-VL/PP-OCR 系模型, 整图文本识别)"""

    def __init__(self, conf: dict | None = None):
        """
        :param conf: 动态配置(model_config 映射), 可含:
            - model: 模型名(默认 PaddleOCR-VL-1.6)
            - url: jobs 端点地址(默认官方托管地址)
            - api_key: AI Studio Access Token(必填, 缺失时报错提示)
            - timeout: 单次 HTTP 请求超时秒数(默认 60)
        """
        self._conf = conf or {}

    @property
    def _api_key(self) -> str:
        api_key = str(self._conf.get("api_key") or "").strip()
        if not api_key:
            raise RuntimeError("PaddleOCR 缺少 api_key: 请在模型配置中填写 AI Studio Access Token")
        return api_key

    @staticmethod
    def _encode_png_b64(image_cv) -> str:
        """cv2 图像编码为 PNG base64(cv2 延迟导入, 启动时不加载重型依赖)"""
        import cv2

        ok, buf = cv2.imencode(".png", image_cv)
        if not ok:
            raise RuntimeError("图片编码失败, 无法上传 PaddleOCR")
        return base64.b64encode(buf.tobytes()).decode()

    @staticmethod
    def _extract_text(lines: list) -> str:
        """从 JSONL 结果抽取整图纯文本: 优先版面块内容, 回退 markdown/OCR 文本"""
        for line_obj in lines:
            result = (line_obj or {}).get("result") or {}
            # 文档解析(PaddleOCR-VL 系): 按版面顺序拼接块内容
            for item in result.get("layoutParsingResults") or []:
                blocks = (item.get("prunedResult") or {}).get("parsing_res_list") or []
                texts = [
                    str(b.get("block_content") or "").strip()
                    for b in blocks
                    if str(b.get("block_content") or "").strip()
                ]
                if texts:
                    return "\n".join(texts)
                markdown = (item.get("markdown") or {}).get("text")
                if markdown and str(markdown).strip():
                    return str(markdown).strip()
            # 经典 OCR(PP-OCR 系): rec_texts 按行拼接
            for item in result.get("ocrResults") or []:
                texts = [str(t).strip() for t in ((item.get("prunedResult") or {}).get("rec_texts") or []) if str(t).strip()]
                if texts:
                    return "\n".join(texts)
        return ""

    def _poll_result(self, headers: dict, job_id: str) -> list:
        """轮询任务状态, 完成后下载并解析 JSONL 结果"""
        import httpx

        timeout = float(self._conf.get("timeout") or _DEFAULT_TIMEOUT)
        budget = float(self._conf.get("poll_timeout") or _DEFAULT_POLL_BUDGET)
        deadline = time.monotonic() + budget
        with httpx.Client(timeout=timeout) as client:
            while time.monotonic() < deadline:
                resp = client.get(f"{str(self._conf.get('url') or _DEFAULT_JOBS_URL).rstrip('/')}/{job_id}", headers=headers)
                if resp.status_code >= 400:
                    raise RuntimeError(f"PaddleOCR 状态查询失败({resp.status_code}): {resp.text[:300]}")
                data = (resp.json() or {}).get("data") or {}
                state = data.get("state")
                if state == "done":
                    json_url = (data.get("resultUrl") or {}).get("jsonUrl")
                    if not json_url:
                        raise RuntimeError(f"PaddleOCR 任务完成但缺少结果地址: {resp.text[:300]}")
                    raw = client.get(json_url)
                    if raw.status_code >= 400:
                        raise RuntimeError(f"PaddleOCR 结果下载失败({raw.status_code}): {raw.text[:300]}")
                    return [json.loads(x) for x in raw.text.strip().splitlines() if x.strip()]
                if state == "failed":
                    raise RuntimeError(f"PaddleOCR 任务失败: {data.get('errorMsg') or resp.text[:300]}")
                time.sleep(_POLL_INTERVAL)
        raise RuntimeError("PaddleOCR 任务轮询超时")

    def recognize(self, image_cv) -> dict:
        """上传图片识别文字, 返回与本地流水线同构的结果

        :param image_cv: cv2 图像(numpy.ndarray)
        :return: {"ts": {"total": 秒}, "results": [{"box", "text", "score"}], "engine": "paddle"}
        """
        import numpy as np

        if not isinstance(image_cv, np.ndarray):
            raise RuntimeError("PaddleOCR 仅支持 cv2 图像输入")
        h, w = image_cv.shape[:2]
        image_b64 = self._encode_png_b64(image_cv)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = str(self._conf.get("url") or _DEFAULT_JOBS_URL).rstrip("/")
        start = time.time()
        try:
            import httpx

            with httpx.Client(timeout=float(self._conf.get("timeout") or _DEFAULT_TIMEOUT)) as client:
                resp = client.post(
                    url,
                    headers=headers,
                    data={
                        "model": str(self._conf.get("model") or "PaddleOCR-VL-1.6"),
                        "optionalPayload": json.dumps({"visualize": False}),
                    },
                    files={"file": ("image.png", base64.b64decode(image_b64), "image/png")},
                )
        except Exception as e:
            raise RuntimeError(f"PaddleOCR 任务提交失败: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(f"PaddleOCR 任务提交失败({resp.status_code}): {resp.text[:500]}")
        job_id = (resp.json() or {}).get("data", {}).get("jobId")
        if not job_id:
            raise RuntimeError(f"PaddleOCR 任务提交未返回 jobId: {resp.text[:300]}")
        text = self._extract_text(self._poll_result(headers, job_id))
        if not text:
            raise RuntimeError("PaddleOCR 未返回识别文本")
        # 与本地流水线结果同构: box 为整图矩形(JSON 可序列化列表)
        return {
            "ts": {"total": round(time.time() - start, 3)},
            "results": [{"box": [[0, 0], [w, 0], [w, h], [0, h]], "text": text, "score": 1.0}],
            "engine": "paddle",
        }

    def parse_document(self, data: bytes, filename: str) -> str:
        """整份文档解析(PaddleOCR-VL 系): 上传原始文件 → 轮询 → 抽取纯文本

        与 ``recognize`` 的区别: 不要求 cv2 图像, pdf 可整份提交, 由服务端完成
        版面分析与阅读顺序还原。

        :param data: 文件原始字节(pdf/png/jpg)
        :param filename: 文件名(用于推断 MIME)
        :return: 文档文本(版面块按阅读顺序拼接, 或 markdown 回退)
        """
        suffix = Path(filename or "").suffix.lower()
        mime = _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = str(self._conf.get("url") or _DEFAULT_JOBS_URL).rstrip("/")
        try:
            import httpx

            with httpx.Client(
                timeout=float(self._conf.get("timeout") or _DEFAULT_TIMEOUT)
            ) as client:
                resp = client.post(
                    url,
                    headers=headers,
                    data={
                        "model": str(self._conf.get("model") or "PaddleOCR-VL-1.6"),
                        "optionalPayload": json.dumps({"visualize": False}),
                    },
                    files={
                        "file": (
                            filename or f"document{suffix or '.bin'}",
                            data,
                            mime,
                        )
                    },
                )
        except Exception as e:
            raise RuntimeError(f"PaddleOCR 文档提交失败: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(
                f"PaddleOCR 文档提交失败({resp.status_code}): {resp.text[:500]}"
            )
        job_id = (resp.json() or {}).get("data", {}).get("jobId")
        if not job_id:
            raise RuntimeError(f"PaddleOCR 文档提交未返回 jobId: {resp.text[:300]}")
        text = self._extract_text(self._poll_result(headers, job_id))
        if not text:
            raise RuntimeError("PaddleOCR 文档解析未返回文本")
        return text
