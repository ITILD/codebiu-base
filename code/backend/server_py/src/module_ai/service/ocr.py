"""OCR 服务门面: 在线(外部服务)文字识别统一入口

模型能力全部通过外部服务接入(基础框架不内置本地推理):
    - 引擎: DashscopeOCR(阿里云百炼 qwen-vl-ocr) / PaddleOCROnline(PaddleOCR 官方云 API),
      由 ModelEntryService 按 server_type/extra.protocol 分派
    - 配置解析/引擎构建/缓存统一委托 ModelEntryService(service/model_entry.py):
      model_config 表(model_type=ocr, server_type=dashscope/online)驱动,
      按 updated_at 缓存引擎(配置变更自动重建); 无配置时给出可操作错误提示
"""
import asyncio
import logging
from typing import Protocol, runtime_checkable

from common.utils.media.file_format import bytes_to_cv2
from module_ai.do.capability import OcrLine, OcrResult
from module_ai.service.model_config import ModelEntryService, get_model_entry

logger = logging.getLogger(__name__)


@runtime_checkable
class OcrCapability(Protocol):
    """文字识别能力契约: 图片识别 + 整份文档识别(如 PaddleOCR-VL)

    其他模块面向本契约编程, 具体实现由 ``module_ai.dependencies.ocr`` 注入。
    """

    async def recognize_image(
        self, image: bytes, *, user_id: str | None = None
    ) -> OcrResult:
        """识别单张图片中的文字(字节输入, 不要求调用方掌握图像库)"""
        ...

    async def recognize_document(
        self, data: bytes, filename: str, *, user_id: str | None = None
    ) -> OcrResult:
        """识别整份文档(pdf/图片), 由支持文档解析的 OCR 引擎实现"""
        ...


class OcrService:
    """在线 OCR 服务门面: 识别统一走外部服务, 引擎解析/缓存委托统一模型入口"""

    def __init__(self, model_entry: ModelEntryService | None = None):
        """依赖注入构造器: 统一入口缺省取全局单例"""
        self._entry = model_entry or get_model_entry()

    async def _get_engine(self, user_id: str | None = None):
        """按统一入口解析 OCR 在线模型配置并获取引擎实例(用户绑定优先于全局配置)"""
        return await self._entry.get_engine("ocr", user_id=user_id)

    async def recognize(
        self,
        image_cv,
        lang: str = "",
        inpaint: bool = False,
        user_id: str | None = None,
    ) -> dict:
        """执行文字识别(在线整图识别, 语言自动检测)

        Args:
            image_cv: 输入图像(OpenCV 格式 numpy.ndarray)
            lang: 兼容参数(在线模型自动检测语种, 忽略)
            inpaint: 兼容参数(本地方案的文字消除已下线, 忽略)
            user_id: 当前用户ID(用户绑定的 ocr 模型优先, 未纳入绑定时走全局默认)

        Returns:
            {"ts": {"total": 秒}, "results": [{index, box, text, score}], "engine": "dashscope"}
        """
        engine = await self._get_engine(user_id)
        # 引擎为同步实现(内部同步 httpx + 轮询 sleep, 最长可达数分钟),
        # 必须放入线程池, 否则单个 OCR 请求会阻塞整个事件循环
        result = await asyncio.to_thread(engine.recognize, image_cv)
        # 补充行序号(前端表格展示用)
        for i, item in enumerate(result.get("results", [])):
            item.setdefault("index", i)
        return result

    async def segment_layout(
        self, image_cv, detect: bool, classify: bool, lang: str, inpaint=False, user_id: str | None = None
    ) -> dict:
        """文字识别(在线整图识别无坐标框, 分栏分段不适用, 与 recognize 等价)"""
        return await self.recognize(image_cv, lang, inpaint, user_id=user_id)

    async def recognize_all(
        self, image_cv, detect: bool, classify: bool, lang: str, inpaint=False, user_id: str | None = None
    ) -> dict:
        """组合接口: 文字识别(在线整图识别, 版面分析已随本地方案下线, layout 恒为空)"""
        result = await self.recognize(image_cv, lang, inpaint, user_id=user_id)
        result["layout"] = []
        return result

    # ########## 对外契约(OcrCapability): 字节进出, 供其他模块调用 ##########

    async def recognize_image(
        self, image: bytes, *, user_id: str | None = None
    ) -> OcrResult:
        """识别单张图片中的文字(契约口径, 字节输入)

        :param image: 图片原始字节
        :param user_id: 当前用户ID(绑定模型优先)
        :return: 标准 OCR 结果
        """
        image_cv = await asyncio.to_thread(bytes_to_cv2, image)
        if image_cv is None:
            raise ValueError("无法解析该图片(格式不支持或已损坏)")
        raw = await self.recognize(image_cv, user_id=user_id)
        lines = [
            OcrLine(
                text=str(item.get("text") or ""),
                box=item.get("box"),
                score=float(item.get("score") or 1.0),
            )
            for item in raw.get("results") or []
        ]
        return OcrResult(
            text="\n".join(line.text for line in lines if line.text),
            lines=lines,
            engine=str(raw.get("engine") or ""),
            elapsed=float((raw.get("ts") or {}).get("total") or 0.0),
        )

    async def recognize_document(
        self, data: bytes, filename: str, *, user_id: str | None = None
    ) -> OcrResult:
        """识别整份文档(pdf/图片), 由支持文档解析的 OCR 引擎实现

        当前仅 PaddleOCR-VL 系在线引擎具备该能力; 其余 OCR 引擎会给出明确提示。

        :param data: 文件原始字节
        :param filename: 文件名(用于推断 MIME 与内容类型)
        :param user_id: 当前用户ID(绑定模型优先)
        :return: 标准 OCR 结果(整份文档合并为一个文本块)
        """
        engine = await self._get_engine(user_id)
        parse_document = getattr(engine, "parse_document", None)
        if parse_document is None:
            raise RuntimeError(
                f"当前 OCR 引擎 {type(engine).__name__} 不支持整份文档解析, "
                "请改用 PaddleOCR-VL 系在线模型"
            )
        text = await asyncio.to_thread(parse_document, data, filename)
        text = str(text or "").strip()
        return OcrResult(
            text=text,
            lines=[OcrLine(text=text)] if text else [],
            engine=type(engine).__name__,
        )
