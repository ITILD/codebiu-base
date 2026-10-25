"""AI 调用输入限制: token 预算与图片体积(统一口径, 服务层与前端共用一套语义)

约束来源:
- 文本类(chat/embeddings/rerank): 模型配置 input_tokens(输入 token 上限)
- 生图(参考图): 百炼 qwen-image 单图上限 10MB, 超限自动压缩到安全体积

设计原则:
- 单位统一 (used, limit, unit), 前端直接渲染 "已输入 X / 限制 Y"
- 压缩/截断不改变调用方语义, 只在边界处兜底, 失败给出可读文案
"""
import base64
import logging
from io import BytesIO

from module_ai.utils.llm.token.tokenizer import Tokenizer

logger = logging.getLogger(__name__)

# 百炼生图参考图体积上限(10MB)与安全目标(留出 base64 膨胀与网关开销余量)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SAFE_IMAGE_BYTES = 9 * 1024 * 1024
# 参考图最长边与压缩下限(避免无损循环压缩到不可用)
MAX_IMAGE_EDGE = 2048
MIN_IMAGE_EDGE = 128
# token 计数统一回退编码(非 OpenAI 系模型近似估算, 与既有统计口径一致)
TOKEN_COUNT_MODEL = "qwen-plus"

_tokenizer = Tokenizer()


def _decode_image(data: str) -> tuple[bytes, str] | None:
    """解析 data URL / 裸 base64 为 (原始字节, mime)

    :return: http(s) 地址或空内容返回 None(交由下游服务处理)
    :raises ValueError: base64 内容非法
    """
    raw = (data or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None
    try:
        if raw.startswith("data:"):
            header, _, payload = raw.partition(",")
            mime = header[5:].split(";")[0] or "image/png"
            return base64.b64decode(payload), mime
        return base64.b64decode(raw), "image/png"
    except Exception as e:
        raise ValueError("参考图内容无法解析, 请重新上传有效的图片文件") from e


def compress_reference_image(
    data: str,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
    max_edge: int = MAX_IMAGE_EDGE,
) -> tuple[str, dict]:
    """把超限参考图自动压缩到上限内(缩放 + JPEG 重编码)

    :param data: 参考图(data URL / 裸 base64 / http URL)
    :param max_bytes: 允许的最大体积
    :param max_edge: 最长边上限
    :return: (可直接下发的参考图, 度量信息 {original_bytes, bytes, width, height, compressed})
    """
    info = {"original_bytes": 0, "bytes": 0, "width": 0, "height": 0, "compressed": False}
    decoded = _decode_image(data)
    if decoded is None:
        # http(s) 地址: 不本地处理, 由下游服务校验
        return data, info
    raw, _mime = decoded
    info["original_bytes"] = len(raw)
    info["bytes"] = len(raw)
    if len(raw) <= max_bytes:
        return data, info

    from PIL import Image

    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception as e:
        raise ValueError(f"参考图无法解析(仅支持 PNG/JPG/WEBP 等常见格式): {e}") from e

    # 先按最长边缩放(手机原图常见 4000px+, 缩到 2048 已足够生成)
    if max(img.size) > max_edge:
        img.thumbnail((max_edge, max_edge), Image.LANCZOS)
    img = img.convert("RGB")

    target = min(max_bytes, SAFE_IMAGE_BYTES)
    buf = BytesIO()
    for quality in (88, 80, 72, 64, 56, 48):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= target:
            break
    # 质量降到最低仍超限: 循环缩图直到达标(尺寸不许低于 MIN_IMAGE_EDGE)
    while buf.tell() > target and max(img.size) > MIN_IMAGE_EDGE:
        img = img.resize(
            (max(1, int(img.width * 0.8)), max(1, int(img.height * 0.8))),
            Image.LANCZOS,
        )
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)

    payload = base64.b64encode(buf.getvalue()).decode("ascii")
    info.update(
        bytes=len(buf.getvalue()),
        width=img.width,
        height=img.height,
        compressed=True,
    )
    logger.info(
        "参考图超限已自动压缩: %.1fMB -> %.1fMB (%dx%d)",
        info["original_bytes"] / 1048576,
        info["bytes"] / 1048576,
        img.width,
        img.height,
    )
    return f"data:image/jpeg;base64,{payload}", info


def friendly_remote_error(message: str) -> str:
    """把远端生图错误文案转成用户可执行的中文提示"""
    text = str(message or "")
    lowered = text.lower()
    if "file size exceeds" in lowered or "10485760" in lowered:
        return "参考图超过 10MB 上限且自动压缩后仍超限, 请换一张更小的图片后重试"
    if "model not exist" in lowered or "model_not_found" in lowered:
        return "生图模型不存在: 请检查模型名称与服务方案是否匹配"
    if "invalid api" in lowered or "401" in lowered or "authentication" in lowered:
        return "生图服务鉴权失败: 请检查 api_key 是否正确"
    return text


def count_tokens(text: str) -> int:
    """统计文本 token 数(与既有对话统计口径一致, 非 OpenAI 系近似估算)"""
    if not text:
        return 0
    return _tokenizer.count_tokens(text, TOKEN_COUNT_MODEL)[0]


def messages_tokens(messages: list) -> int:
    """统计消息列表 token 数(兼容字符串与 LangChain 消息 content 列表)"""
    total = 0
    for msg in messages:
        content = getattr(msg, "content", msg)
        if isinstance(content, str):
            total += count_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += count_tokens(str(part.get("text") or ""))
                else:
                    total += count_tokens(str(part))
        else:
            total += count_tokens(str(content or ""))
    return total


def limit_info(used: int, limit: int, unit: str = "token") -> dict:
    """构造统一限制度量 {used, limit, unit, exceeded}(limit<=0 视为不限)"""
    return {
        "used": int(used or 0),
        "limit": int(limit or 0),
        "unit": unit,
        "exceeded": bool(limit and used > limit),
    }
