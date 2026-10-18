"""Office 本地解析器: docx/pptx 纯标准库解析, 不依赖外部服务。

背景: MinerU 远程 API 仅支持 pdf 与图片, docx/pptx 直传必失败
("parsing failed, please try again later"), 导致 Office 文档永远无法入库。
本解析器用 zipfile + ElementTree 直接读取 OOXML, 输出与 MinerU 对齐的 Chunk:

- docx: 段落(outlineLvl/pStyle Heading* → TITLE) + 表格 → markdown TABLE
- pptx: 每页 slide, 标题占位符 → TITLE(级别1), 正文 → TEXT, 表格 → TABLE
- .doc/.ppt 为二进制旧格式, 标准库无法解析, 给出明确的另存提示
"""
import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.do.chunk import Chunk, ContentType, Position

logger = logging.getLogger(__name__)

_NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_NS_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"

# 大表格阈值(字符数), 与 MinerUParser 口径一致
_TABLE_LARGE_THRESHOLD = 2000


class OfficeParser(BaseParser):
    """docx/pptx 本地解析器(zipfile + ElementTree, 零外部依赖)"""

    async def extract(self, file: Path) -> list[Chunk]:
        """按后缀路由 docx/pptx 解析(异步签名与引擎解析器对齐, CPU 计算可忽略 await)"""
        suffix = file.suffix.lower()
        if suffix == ".docx":
            return self._extract_docx(file)
        if suffix == ".pptx":
            return self._extract_pptx(file)
        raise ValueError(f"Office 本地解析器仅支持 docx/pptx, {suffix} 请先另存为对应新格式")

    # ############################# docx #############################

    def _extract_docx(self, file: Path) -> list[Chunk]:
        """docx: 按文档顺序遍历段落与表格"""
        with zipfile.ZipFile(file) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        body = root.find(f"{_NS_W}body")
        if body is None:
            return []

        chunks: list[Chunk] = []
        for element in body:
            if element.tag == f"{_NS_W}p":
                chunk = self._docx_paragraph(element)
                if chunk:
                    chunks.append(chunk)
            elif element.tag == f"{_NS_W}tbl":
                rows = self._docx_table_rows(element)
                chunks.extend(self._table_chunks(rows, page=1))
        return chunks

    def _docx_paragraph(self, p) -> Chunk | None:
        """docx 段落: outlineLvl / pStyle(Heading*) 判定标题级别"""
        text = "".join(t.text or "" for t in p.iter(f"{_NS_W}t")).strip()
        if not text:
            return None
        level = self._docx_heading_level(p)
        if level:
            return Chunk(
                content=text,
                content_type=ContentType.TITLE,
                position=Position(page=1, heading_level=level),
            )
        return Chunk(content=text, position=Position(page=1))

    def _docx_heading_level(self, p) -> int | None:
        """标题级别: outlineLvl(0-based) 优先, pStyle Heading*/标题 N 兜底"""
        ppr = p.find(f"{_NS_W}pPr")
        if ppr is None:
            return None
        outline = ppr.find(f"{_NS_W}outlineLvl")
        if outline is not None and outline.get(f"{_NS_W}val", "").isdigit():
            return int(outline.get(f"{_NS_W}val")) + 1
        style = ppr.find(f"{_NS_W}pStyle")
        if style is not None:
            val = style.get(f"{_NS_W}val", "") or ""
            m = re.search(r"(?:heading|标题)\s*(\d+)", val, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    def _docx_table_rows(self, tbl) -> list[list[str]]:
        """docx 表格 → 二维文本网格"""
        rows: list[list[str]] = []
        for tr in tbl.findall(f"{_NS_W}tr"):
            cells: list[str] = []
            for tc in tr.findall(f"{_NS_W}tc"):
                cells.append(" ".join(
                    t.text or "" for t in tc.iter(f"{_NS_W}t")
                ).strip())
            if cells:
                rows.append(cells)
        return rows

    # ############################# pptx #############################

    def _extract_pptx(self, file: Path) -> list[Chunk]:
        """pptx: 按 slide 序号遍历, 每页输出标题/正文/表格"""
        with zipfile.ZipFile(file) as zf:
            slide_names = sorted(
                (n for n in zf.namelist()
                 if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[-1]).group()),
            )
            chunks: list[Chunk] = []
            for page, name in enumerate(slide_names, start=1):
                root = ET.fromstring(zf.read(name))
                for sp in root.iter(f"{_NS_P}sp"):
                    if self._is_title_shape(sp):
                        text = self._shape_text(sp)
                        if text:
                            chunks.append(Chunk(
                                content=text,
                                content_type=ContentType.TITLE,
                                position=Position(page=page, heading_level=1),
                            ))
                    else:
                        text = self._shape_text(sp)
                        if text:
                            chunks.append(Chunk(content=text, position=Position(page=page)))
                # 图形框表格(graphicFrame 内 a:tbl)
                for tbl in root.iter(f"{_NS_A}tbl"):
                    rows = self._pptx_table_rows(tbl)
                    chunks.extend(self._table_chunks(rows, page=page))
        return chunks

    def _is_title_shape(self, sp) -> bool:
        """标题占位符判定(ph type=title/ctrTitle)"""
        for ph in sp.iter(f"{_NS_P}ph"):
            if ph.get("type") in ("title", "ctrTitle"):
                return True
        return False

    def _shape_text(self, sp) -> str:
        """形状内全部 a:t 文本按段落聚合"""
        paragraphs: list[str] = []
        for p in sp.iter(f"{_NS_A}p"):
            text = "".join(t.text or "" for t in p.iter(f"{_NS_A}t")).strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)

    def _pptx_table_rows(self, tbl) -> list[list[str]]:
        """pptx 表格 → 二维文本网格"""
        rows: list[list[str]] = []
        for tr in tbl.findall(f"{_NS_A}tr"):
            cells = [" ".join(t.text or "" for t in tc.iter(f"{_NS_A}t")).strip()
                     for tc in tr.findall(f"{_NS_A}tc")]
            if cells:
                rows.append(cells)
        return rows

    # ############################# 公共 #############################

    def _table_chunks(self, rows: list[list[str]], page: int) -> list[Chunk]:
        """表格 → markdown(超阈值拆表头+表内容, 口径与 MinerUParser 一致)"""
        if not rows:
            return []
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        text_len = sum(len(c) for r in rows for c in r)
        header_md = self._rows_to_md_table([rows[0]], with_separator=True)
        if text_len <= _TABLE_LARGE_THRESHOLD or len(rows) == 1:
            body_md = self._rows_to_md_table(rows[1:], with_separator=False)
            md = header_md + (f"\n{body_md}" if body_md else "")
            return [Chunk(content=md, content_type=ContentType.TABLE,
                          position=Position(page=page), metadata={"mergeable": "false"})]
        body_md = self._rows_to_md_table(rows[1:], with_separator=False)
        return [
            Chunk(content=header_md, content_type=ContentType.TABLE_HEADER,
                  position=Position(page=page), metadata={"mergeable": "false"}),
            Chunk(content=body_md, content_type=ContentType.TABLE_CONTENT,
                  position=Position(page=page), metadata={"mergeable": "false"}),
        ]

    @staticmethod
    def _rows_to_md_table(rows: list[list[str]], *, with_separator: bool) -> str:
        """渲染紧凑 markdown 表格"""
        lines: list[str] = []
        for i, row in enumerate(rows):
            cells = [c.replace("|", "\\|") for c in row]
            lines.append("| " + " | ".join(cells) + " |")
            if i == 0 and with_separator:
                lines.append("|" + "|".join("---" for _ in row) + "|")
        return "\n".join(lines)
