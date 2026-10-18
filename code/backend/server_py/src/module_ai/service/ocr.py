"""OCR 服务门面: 在线(外部服务)文字识别统一入口

模型能力全部通过外部服务接入(基础框架不内置本地推理):
    - 引擎: DashscopeOCR(阿里云百炼 qwen-vl-ocr) / PaddleOCROnline(PaddleOCR 官方云 API),
      由 ModelEntryService 按 server_type/extra.protocol 分派
    - 配置解析/引擎构建/缓存统一委托 ModelEntryService(service/model_entry.py):
      model_config 表(model_type=ocr, server_type=dashscope/online)驱动,
      按 updated_at 缓存引擎(配置变更自动重建); 无配置时给出可操作错误提示
"""
import logging

from module_ai.service.model_entry import ModelEntryService, get_model_entry

logger = logging.getLogger(__name__)


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
        result = engine.recognize(image_cv)
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
