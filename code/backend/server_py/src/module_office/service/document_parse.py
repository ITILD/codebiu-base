"""文档解析模块 document_parse 业务逻辑层

职责: 组装解析上下文(用户ID + module_ai 能力) → 按解析方案选择引擎 →
引擎产出统一 Chunk → 返回带尝试链路的结果。本层不直接调用任何模型服务。
"""

from pathlib import Path

from module_office.do.parse import (
    ParseAttempt,
    ParseContext,
    ParsePlan,
    ParseResult,
)
from module_office.utils.file_parse.do.chunk import Chunk
from module_office.utils.file_parse.registry import engine_registry


class DocumentParseService:
    """文件解析服务(引擎注册表 + 模块化能力注入)"""

    def __init__(self, vision=None, ocr=None):
        """依赖注入构造器

        :param vision: 视觉理解能力(VisionCapability), 缺省取 module_ai 单例
        :param ocr: OCR 能力(OcrCapability), 缺省取 module_ai 单例
        """
        if vision is None or ocr is None:
            # 延迟导入: 只在真正构造服务时触碰 module_ai 依赖, 避免模块导入期循环
            from module_ai.dependencies.llm import get_vision_service

            vision = vision or get_vision_service()
            if ocr is None:
                from module_ai.dependencies.ocr import get_ocr_service

                ocr = get_ocr_service()
        self._vision = vision
        self._ocr = ocr

    async def parse(
        self,
        file_path: Path,
        *,
        user_id: str | None = None,
        plan: ParsePlan | None = None,
        engine: str | None = None,
    ) -> ParseResult:
        """解析文件并返回分块、命中引擎与尝试链路

        :param file_path: 文件路径
        :param user_id: 当前用户ID(解析其绑定的视觉/OCR 模型)
        :param plan: 解析方案(主引擎/备用引擎/媒体策略), 缺省为 auto
        :param engine: 显式指定引擎(覆盖 plan)
        :return: 解析结果
        :raises ValueError: 文件后缀无引擎支持
        """
        file_path = Path(file_path)
        plan = plan or ParsePlan()
        ctx = ParseContext(
            user_id=user_id, vision=self._vision, ocr=self._ocr, plan=plan
        )
        parser, descriptor, failed = engine_registry.create(
            file_path, ctx, plan=plan, engine=engine
        )
        chunks = await parser.extract(file_path)
        return ParseResult(
            chunks=chunks,
            engine=descriptor.name,
            attempts=[
                *failed,
                ParseAttempt(engine=descriptor.name, ok=True),
            ],
            source=file_path,
        )

    async def file2chunk(
        self,
        file_path: Path,
        *,
        user_id: str | None = None,
        plan: ParsePlan | None = None,
        engine: str | None = None,
    ) -> list[Chunk]:
        """
        将文件解析为带元数据(内容类型、页码等)的 Chunk 列表

        解析引擎由 EngineRegistry 按后缀与解析方案路由, 上层无需感知具体引擎。

        :param file_path: 文件路径
        :param user_id: 当前用户ID(解析其绑定的视觉/OCR 模型)
        :param plan: 解析方案(主引擎/备用引擎/媒体策略)
        :param engine: 显式指定引擎
        :return: Chunk 列表
        :raises ValueError: 文件后缀不受任何引擎支持
        """
        result = await self.parse(
            file_path, user_id=user_id, plan=plan, engine=engine
        )
        return result.chunks

    async def file2markdown(
        self,
        file_path: Path,
        *,
        user_id: str | None = None,
        plan: ParsePlan | None = None,
        engine: str | None = None,
    ) -> str:
        """
        将文件解析为 Markdown 格式

        :param file_path: 文件路径
        :param user_id: 当前用户ID(解析其绑定的视觉/OCR 模型)
        :param plan: 解析方案
        :param engine: 显式指定引擎
        :return: Markdown 文本
        """
        chunks = await self.file2chunk(
            file_path, user_id=user_id, plan=plan, engine=engine
        )
        return "\n".join(chunk.content or "" for chunk in chunks)
