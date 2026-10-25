"""PaddleOCR-VL 整文件解析引擎(pdf/图片)

与 MinerU 同为「整文件版式解析」外部服务, 但本引擎不直接对接 HTTP,
而是通过 ``module_ai`` 的 ``OcrCapability.recognize_document`` 执行:
office 只负责格式路由与结果归一, 具体的 OCR 模型配置/鉴权/轮询由 ai 模块维护。
"""

import asyncio
from pathlib import Path

from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.do.chunk import Chunk, ContentType, Position


class PaddleOCRParser(BaseParser):
    """PaddleOCR 引擎解析器(依赖 ctx.ocr 能力注入)"""

    async def extract(self, file: Path) -> list[Chunk]:
        """整份文档识别: 原文件字节 -> OCR 文本 -> 单个 TEXT 分块

        :param file: 待解析文件(pdf/png/jpg/jpeg)
        :return: 文本分块列表
        """
        ocr = self.ctx.ocr
        if ocr is None:
            raise RuntimeError("未注入 OCR 能力, 无法使用 PaddleOCR 引擎")
        data = await asyncio.to_thread(file.read_bytes)
        result = await ocr.recognize_document(
            data, file.name, user_id=self.ctx.user_id
        )
        text = (result.text or "").strip()
        if not text:
            raise RuntimeError("PaddleOCR 未返回文本内容")
        return [
            Chunk(
                content=text,
                content_type=ContentType.TEXT,
                position=Position(page=1),
            )
        ]
