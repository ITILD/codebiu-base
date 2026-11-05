"""OCR 服务门面: 在线(外部服务)文字识别统一入口

模型能力全部通过外部服务接入(基础框架不内置本地推理):
    - 引擎: DashscopeOCR(阿里云百炼 qwen-vl-ocr) / PaddleOCROnline(PaddleOCR 官方云 API) /
      OXROnline(OXR 1.0 官方同步解析), 由 ModelEntryService 按 server_type/extra.protocol 分派
    - 配置解析/引擎构建/缓存统一委托 ModelEntryService(service/model_config.py):
      model_config 表(model_type=ocr, server_type=dashscope/online)驱动,
      按 updated_at 缓存引擎(配置变更自动重建); 无配置时给出可操作错误提示
    - 多解析器降级链: 后台可添加多条 OCR 配置(不同厂商/Key), 按
      用户绑定 → 默认公共 → 其余生效配置 顺序逐个尝试, 单条失败自动切下一条
"""
import asyncio
import logging
from typing import Protocol, runtime_checkable

from common.utils.media.file_format import bytes_to_cv2
from module_ai.do.capability import OcrLine, OcrResult
from module_ai.service.model_config import (
    ModelEntryService,
    ModelNotConfiguredError,
    get_model_entry,
)

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

    async def _get_engines(self, user_id: str | None = None) -> list:
        """按降级链获取全部 OCR 引擎实例

        顺序: 用户绑定 → 默认公共模型 → 其余生效配置(后台新增顺序)。
        用户可在后台添加多条 OCR 配置(如 PaddleOCR-VL 1.6 + OXR 1.0),
        识别失败时自动切换下一条, 充分利用各厂商免费额度。
        """
        configs = await self._entry.list_candidate_configs("ocr", user_id=user_id)
        if not configs:
            raise ModelNotConfiguredError(
                "未配置 ocr 模型: 请在后台「模型配置」中添加 model_type=ocr 的记录"
            )
        return [
            await self._entry.get_engine("ocr", model_id=config.id)
            for config in configs
        ]

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
        engines = await self._get_engines(user_id)
        errors: list[str] = []
        for engine in engines:
            try:
                # 引擎为同步实现(内部同步 httpx + 轮询 sleep, 最长可达数分钟),
                # 必须放入线程池, 否则单个 OCR 请求会阻塞整个事件循环
                result = await asyncio.to_thread(engine.recognize, image_cv)
            except Exception as e:  # 单条配置失败(欠费/限流/服务不可达)时切换下一条
                logger.warning("OCR 引擎 %s 识别失败, 尝试下一条: %s", type(engine).__name__, e)
                errors.append(f"{type(engine).__name__}: {e}")
                continue
            # 补充行序号(前端表格展示用)
            for i, item in enumerate(result.get("results", [])):
                item.setdefault("index", i)
            return result
        raise RuntimeError("全部 OCR 引擎识别失败: " + "; ".join(errors))

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
        engines = await self._get_engines(user_id)
        # 仅支持整份文档解析的引擎参与(PaddleOCR-VL 系 / OXR); 纯图片识别引擎跳过
        capable = [e for e in engines if getattr(e, "parse_document", None)]
        if not capable:
            names = ", ".join(type(e).__name__ for e in engines)
            raise RuntimeError(
                f"当前 OCR 引擎均不支持整份文档解析({names}), "
                "请改用 PaddleOCR-VL / OXR 系在线模型"
            )
        errors: list[str] = []
        for engine in capable:
            try:
                text = await asyncio.to_thread(engine.parse_document, data, filename)
                text = str(text or "").strip()
                if not text:
                    raise RuntimeError("未返回文本内容")
            except Exception as e:  # 单条解析失败(额度耗尽/超大文件)时切换下一条
                logger.warning("OCR 文档解析引擎 %s 失败, 尝试下一条: %s", type(engine).__name__, e)
                errors.append(f"{type(engine).__name__}: {e}")
                continue
            return OcrResult(
                text=text,
                lines=[OcrLine(text=text)] if text else [],
                engine=type(engine).__name__,
            )
        raise RuntimeError("全部 OCR 引擎文档解析失败: " + "; ".join(errors))
