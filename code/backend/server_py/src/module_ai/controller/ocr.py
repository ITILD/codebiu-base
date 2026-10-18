"""OCR 控制器: 在线(外部服务)文字识别

接口(路由前缀 /ocr):
    - POST /             文字识别(图片上传)
    - POST /all          文字识别(与 / 等价, 兼容旧路由)
    - POST /all-base64   文字识别(base64 图片直传)
    - GET  /languages    返回支持语言列表(在线模型自动检测语种, 固定返回 auto)

具体业务逻辑见 module_ai/service/ocr.py(OcrService)。
"""
import base64
import logging

from fastapi import APIRouter, Depends, Form, UploadFile, status

from common.utils.media.file_format import bytes_to_cv2
from module_ai.config.server import module_app
from module_ai.dependencies.ocr import get_ocr_service
from module_ai.do.ocr import Base64File
from module_ai.service.ocr import OcrService
from module_authorization.dependencies.auth import get_current_user_id_optional

logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, summary="文字识别")
async def recognize(
    image: UploadFile,
    lang: str = Form("", description="兼容参数(在线模型自动检测语种)"),
    ocr_service: OcrService = Depends(get_ocr_service),
    current_user_id: str | None = Depends(get_current_user_id_optional),
):
    """对上传图片执行 OCR 文字识别(在线外部服务)

    :param image: 上传的图片文件
    :param lang: 兼容参数(在线模型自动检测语种)
    :return: 识别结果 {ts, results: [{index, box, text, score}], engine}
    """
    image_bytes = await image.read()
    image_cv = bytes_to_cv2(image_bytes)
    return await ocr_service.recognize(image_cv, lang, user_id=current_user_id)


@router.post("/all", status_code=status.HTTP_201_CREATED, summary="文字识别(兼容旧路由)")
async def recognize_all(
    image: UploadFile,
    lang: str = Form("", description="兼容参数(在线模型自动检测语种)"),
    ocr_service: OcrService = Depends(get_ocr_service),
    current_user_id: str | None = Depends(get_current_user_id_optional),
):
    """组合接口兼容: 文字识别(版面分析已随本地方案下线, layout 恒为空)

    :param image: 上传的图片文件
    :param lang: 兼容参数(在线模型自动检测语种)
    :return: 识别结果(含空 layout 字段以兼容旧响应结构)
    """
    image_bytes = await image.read()
    image_cv = bytes_to_cv2(image_bytes)
    return await ocr_service.recognize_all(image_cv, True, True, lang, user_id=current_user_id)


@router.post(
    "/all-base64",
    status_code=status.HTTP_201_CREATED,
    summary="文字识别(base64 图片直传)",
)
async def recognize_base64(
    base64_file: Base64File,
    ocr_service: OcrService = Depends(get_ocr_service),
    current_user_id: str | None = Depends(get_current_user_id_optional),
):
    """同 /all 接口,但图片以 base64 编码传入(便于前端直传)

    :param base64_file: 含 base64 图片与识别参数的请求体
    :return: 识别结果(含空 layout 字段以兼容旧响应结构)
    """
    image_bytes = base64.b64decode(base64_file.image_base64)
    image_cv = bytes_to_cv2(image_bytes)
    return await ocr_service.recognize_all(
        image_cv, True, True, base64_file.lang, base64_file.inpaint,
        user_id=current_user_id,
    )


@router.get("/languages", status_code=status.HTTP_201_CREATED, summary="返回可用语言列表")
def get_languages():
    """返回支持语言列表(在线 OCR 模型自动检测语种, 固定返回 auto)"""
    return [{"code": "auto", "name": "自动识别"}]


module_app.include_router(router, prefix="/ocr", tags=["ocr识别"])
