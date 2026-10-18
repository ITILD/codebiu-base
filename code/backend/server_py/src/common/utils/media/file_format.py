"""媒体格式工具: base64/PIL/URL/字节数组互转

cv2/numpy 仅在 bytes_to_cv2 被调用(OCR 接口收到图片)时才加载,
避免 Web 进程启动即把 opencv 拉入内存。
"""

import base64
import io
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from cv2 import Mat


def bytes_to_cv2(image_bytes: bytes) -> "Mat":
    """将字节流转换为cv2格式"""
    import cv2
    import numpy as np

    image_np = np.frombuffer(image_bytes, np.uint8)
    image_cv: Mat = cv2.imdecode(image_np, cv2.IMREAD_COLOR)
    return image_cv


def pil_to_base64(pil_img: Image.Image, quality: int = 85) -> str:
    """将 PIL Image 编码为 base64 字符串(JPEG,quality=85)

    VLM 输入会 resize 到固定分辨率,原图超分辨率被丢弃,故 JPEG 有损不影响识别;
    RGBA 先转 RGB(JPEG 不支持 alpha 通道)。
    """
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def base64_to_url(img_base64: str, mime: str = "image/jpeg") -> str:
    """将 base64 图片字符串转为 data URL(供 VLM image_url 输入)"""
    return f"data:{mime};base64,{img_base64}"
