"""Oxide 解析器: 使用 pdf_oxide + office_oxide 读取 PDF / Office 文档。

两库均为 Pure-Rust 核心(PyO3 绑定), 比传统纯 Python 实现快一个数量级,
且原生覆盖旧版二进制格式(.doc/.xls/.ppt), 这正是纯标准库实现(office
parser.py, zipfile+ElementTree)的盲区。

- pdf_oxide:       PDF 文本/HTML 抽取 + markdown 转换
- office_oxide:    DOC/DOCX/XLS/XLSX/PPT/PPTX 文本抽取 + markdown 转换 + IR

本解析器定位为 MinerU 不可用时的离线兜底, 但能力范围扩大到 PDF 和旧
Office 二进制格式。
"""
from __future__ import annotations

import logging
from pathlib import Path

# 直接以脚本方式运行(debugpy F5 / python parser.py)时 src 不在 sys.path,
# 在导入 module_office 之前自举; 作为包导入时此分支不生效
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.do.chunk import Chunk, ContentType, Position

logger = logging.getLogger(__name__)

# 各库支持的文件后缀
_PDF_SUFFIXES = {".pdf"}
_OFFICE_SUFFIXES = {
    ".doc", ".docx",
    ".xls", ".xlsx",
    ".ppt", ".pptx",
}
_MARKDOWN_SUFFIXES = _PDF_SUFFIXES | _OFFICE_SUFFIXES


class OxideParser(BaseParser):
    """基于 pdf_oxide / office_oxide 的统一解析器。

    用法:
        parser = OxideParser()
        chunks = await parser.extract(Path("report.docx"))
    """

    async def extract(self, file: Path) -> list[Chunk]:
        """按文件后缀路由到对应 oxide 引擎。"""
        suffix = file.suffix.lower()

        if suffix in _PDF_SUFFIXES:
            return self._extract_pdf(file)
        if suffix in _OFFICE_SUFFIXES:
            return self._extract_office(file)

        raise ValueError(f"OxideParser 不支持 {suffix}")

    async def extract_ir(self, file: Path) -> dict:
        """提取文档结构(供 admin 测试端点查看 JSON 结构支持情况)

        - PDF: 无原生 IR, 合成按页结构(page_count + 每页 markdown/text)
        - Office: office_oxide 原生 ``to_ir()`` 结构树(标题/段落/表格/幻灯片等)
        """
        suffix = file.suffix.lower()
        if suffix in _PDF_SUFFIXES:
            from pdf_oxide import PdfDocument

            with PdfDocument(str(file)) as doc:
                pages: list[dict] = []
                for page in doc:
                    idx = page.index + 1
                    try:
                        md = page.markdown(detect_headings=True)
                    except Exception:  # noqa: BLE001 — 单页失败不阻断整册
                        md = page.text
                    pages.append({
                        "page": idx,
                        "width": page.width,
                        "height": page.height,
                        "markdown": (md or "").strip(),
                        "text": (page.text or "").strip(),
                    })
                return {
                    "engine": "pdf_oxide",
                    "format": "pdf",
                    "page_count": len(pages),
                    "tagged_pdf": doc.has_structure_tree(),
                    "pages": pages,
                }

        if suffix in _OFFICE_SUFFIXES:
            from office_oxide import Document

            with Document.open(str(file)) as doc:
                return {
                    "engine": "office_oxide",
                    "format": doc.format,
                    "damage": doc.damage(),
                    "ir": doc.to_ir(),
                }

        raise ValueError(f"OxideParser 不支持 {suffix}")

    # ------------------------------- PDF -------------------------------

    def _extract_pdf(self, file: Path) -> list[Chunk]:
        """pdf_oxide 按页抽取 markdown, 每页一个 Chunk。

        注意: pdf_oxide 的入口是构造函数 ``PdfDocument(path)``,
        没有 ``PdfDocument.open`` 类方法; Page 对象 ``markdown()`` 支持
        ``detect_headings`` 等参数, 失败时逐页退回 ``page.text``。
        """
        from pdf_oxide import PdfDocument

        chunks: list[Chunk] = []
        try:
            with PdfDocument(str(file)) as doc:
                for page in doc:
                    page_idx = page.index + 1
                    try:
                        md = page.markdown(detect_headings=True)
                    except Exception:  # noqa: BLE001 — 单页失败退回纯文本
                        md = page.text
                    text = (md or "").strip()
                    if not text:
                        continue
                    chunks.append(Chunk(
                        content=text,
                        content_type=ContentType.TEXT,
                        position=Position(page=page_idx),
                    ))
        except Exception as exc:  # noqa: BLE001 — 整册失败退回逐页纯文本
            logger.warning("pdf_oxide markdown 解析失败, 退回纯文本: %s", exc)
            with PdfDocument(str(file)) as doc:
                for page in doc:
                    text = (page.text or "").strip()
                    if text:
                        chunks.append(Chunk(
                            content=text,
                            content_type=ContentType.TEXT,
                            position=Position(page=page.index + 1),
                        ))
        return chunks

    # ------------------------------ Office ------------------------------
    def _extract_office(self, file: Path) -> list[Chunk]:
        """office_oxide 统一入口: 新旧格式通吃, 返回 markdown Chunk。"""
        from office_oxide import Document, OfficeOxideError

        chunks: list[Chunk] = []
        try:
            with Document.open(str(file)) as doc:
                fmt = doc.format or doc.format_name or file.suffix.lstrip(".")
                logger.debug("office_oxide detected format: %s", fmt)

                # 优先 markdown, 失败退回纯文本
                try:
                    md = doc.to_markdown()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("to_markdown 失败, 退回 plain_text: %s", exc)
                    md = doc.plain_text() or ""

                text = (md or "").strip()
                if not text:
                    return []

                chunks.append(Chunk(
                    content=text,
                    content_type=ContentType.TEXT,
                    position=Position(page=1),
                    metadata={"format": fmt, "engine": "office_oxide"},
                ))
        except OfficeOxideError as exc:
            # 旧 Office 加密文档会走这里, 给出明确提示
            logger.error("office_oxide 解析失败: %s", exc)
            raise
        return chunks


class OxideParserPlain(BaseParser):
    """纯文本抽取版 —— 只调用 plain_text / page.text, 不做 markdown 转换。

    适合对格式不敏感、只关心原始文本的场景。
    """

    async def extract(self, file: Path) -> list[Chunk]:
        suffix = file.suffix.lower()
        if suffix in _PDF_SUFFIXES:
            return self._extract_pdf_plain(file)
        if suffix in _OFFICE_SUFFIXES:
            return self._extract_office_plain(file)
        raise ValueError(f"OxideParserPlain 不支持 {suffix}")

    def _extract_pdf_plain(self, file: Path) -> list[Chunk]:
        from pdf_oxide import PdfDocument
        chunks: list[Chunk] = []
        with PdfDocument(str(file)) as doc:
            for page in doc:
                text = (page.text or "").strip()
                if text:
                    chunks.append(Chunk(
                        content=text,
                        content_type=ContentType.TEXT,
                        position=Position(page=page.index + 1),
                        metadata={"engine": "pdf_oxide"},
                    ))
        return chunks

    def _extract_office_plain(self, file: Path) -> list[Chunk]:
        from office_oxide import Document
        chunks: list[Chunk] = []
        with Document.open(str(file)) as doc:
            fmt = doc.format or doc.format_name or file.suffix.lstrip(".")
            text = (doc.plain_text() or "").strip()
            if not text:
                return []
            chunks.append(Chunk(
                content=text,
                content_type=ContentType.TEXT,
                position=Position(page=1),
                metadata={"format": fmt, "engine": "office_oxide"},
            ))
        return chunks


async def extract_output(file: Path, out: str) -> dict:
    """Oxide 多形态提取(admin 测试端点用): markdown/json/ir/html/text

    :param file: 文件路径(pdf/doc/docx/xls/xlsx/ppt/pptx)
    :param out: 输出形态
    :return: {"format": 实际格式, "out": 输出形态, "content": str|dict}
    """
    from pdf_oxide import PdfDocument

    suffix = file.suffix.lower()
    fmt = suffix.lstrip(".")
    content: str | dict

    if out in ("ir", "json"):
        result = await OxideParser().extract_ir(file)
        return {"format": result["format"], "out": out, "content": result}

    if suffix in _PDF_SUFFIXES:
        if out == "markdown":
            parser = OxideParser()
        else:
            parser = OxideParserPlain()
        chunks = await parser.extract(file)
        content = "\n\n".join(c.content or "" for c in chunks)
        if out == "html":
            with PdfDocument(str(file)) as doc:
                content = "\n".join(
                    filter(None, (p.html() for p in doc))
                )
    elif suffix in _OFFICE_SUFFIXES:
        from office_oxide import Document

        with Document.open(str(file)) as doc:
            fmt = doc.format
            if out == "markdown":
                content = doc.to_markdown() or doc.plain_text() or ""
            elif out == "html":
                content = doc.to_html() or ""
            elif out == "text":
                content = doc.plain_text() or ""
            else:
                raise ValueError(f"不支持的输出形态: {out}")
    else:
        raise ValueError(f"OxideParser 不支持 {suffix}")

    return {"format": fmt, "out": out, "content": content}

if __name__ == "__main__":
    import asyncio
    import json

    # server_py/temp_source/test: parents = [oxide, file_parse, utils, module_office, src]
    SAMPLE_DIR = Path(__file__).resolve().parents[5] / "temp_source" / "test"

    async def _main() -> None:
        target = (
            Path(sys.argv[1]) if len(sys.argv) > 1
            else SAMPLE_DIR / "文本类pdf标准测试.pdf"
        )
        out = sys.argv[2] if len(sys.argv) > 2 else "markdown"
        result = await extract_output(target, out)
        content = result["content"]
        if isinstance(content, dict):
            print(json.dumps(content, ensure_ascii=False)[:2000])
        else:
            print(f"[{target.name} -> {out}] format={result['format']} {len(content)} 字符")
            print("-" * 60)
            print(content[:2000])

    asyncio.run(_main())