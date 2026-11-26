"""测试 office_oxide 对 doc/docx/xls/xlsx/ppt/pptx 的读取能力。

用 office_oxide 自身的 EditableDocument / Writer 生成测试文件, 避免引入
python-docx/openpyxl/python-pptx 等额外依赖。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from office_oxide import EditableDocument, OfficeOxideError, PptxWriter, XlsxWriter

from module_office.utils.file_parse.oxide import OxideParser, OxideParserPlain

TMPDIR = Path("/tmp/oxide_test")
TMPDIR.mkdir(exist_ok=True)


def make_docx(path: Path) -> None:
    """用 EditableDocument 基于空模板创建 docx。

    office_oxide 目前没有直接"新建" DOCX 的入口, 这里复用一份已有 DOCX
    或退而求其次 —— 用最小 OOXML zip 结构手工生成(不依赖额外库)。
    """
    # 方案: 手工构造最小 docx(zip + [Content_Types].xml + word/document.xml)
    import zipfile

    content_types = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
        "</Types>"
    )
    rels = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "</Relationships>"
    )
    doc_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body>"
        "<w:p><w:r><w:t>Hello Oxide DOCX</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Second line content.</w:t></w:r></w:p>"
        "<w:tbl>"
        "<w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid>"
        "<w:tr><w:tc><w:p><w:r><w:t>A1</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>B1</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>A2</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>B2</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc_xml)


def make_xlsx(path: Path) -> None:
    """用 office_oxide.XlsxWriter 生成 xlsx。

    set_cell(sheet_idx, row, col, value) —— row/col 均为 0-based 整数。
    """
    writer = XlsxWriter()
    idx = writer.add_sheet("Sheet1")
    # header row (row=0)
    writer.set_cell(idx, 0, 0, "Name")
    writer.set_cell(idx, 0, 1, "Age")
    # data rows
    writer.set_cell(idx, 1, 0, "Alice")
    writer.set_cell(idx, 1, 1, 30)
    writer.set_cell(idx, 2, 0, "Bob")
    writer.set_cell(idx, 2, 1, 25)
    writer.save(str(path))


def make_pptx(path: Path) -> None:
    """用 office_oxide.PptxWriter 生成 pptx。"""
    writer = PptxWriter()
    idx = writer.add_slide()            # 返回 slide_index(int)
    writer.set_slide_title(idx, "Test Deck")
    writer.add_slide_text(idx, "First bullet")
    writer.add_slide_text(idx, "Second bullet")
    writer.save(str(path))


def test_parse(name: str, path: Path) -> None:
    print(f"\n{'='*60}")
    print(f"  {name}: {path}")
    print(f"{'='*60}")

    # ---- office_oxide 直接 ----
    import office_oxide
    try:
        with office_oxide.Document.open(str(path)) as doc:
            fmt = doc.format or doc.format_name
            pt = doc.plain_text() or ""
            md = (doc.to_markdown() or "")[:400]
            print(f"[office_oxide] format={fmt!r}")
            print(f"  plain_text ({len(pt)} chars): {pt[:120]!r}...")
            print(f"  to_markdown: {md[:200]}")
    except OfficeOxideError as e:
        print(f"[office_oxide] FAILED: {e}")

    # ---- OxideParser ----
    async def run_parser():
        parser = OxideParser()
        return await parser.extract(path)

    try:
        chunks = asyncio.run(run_parser())
        print(f"[OxideParser] chunks={len(chunks)}")
        for i, c in enumerate(chunks[:3]):
            print(f"  chunk[{i}] pos={c.position} len={len(c.content)} "
                  f"ct={c.content_type} meta={c.metadata}")
            print(f"    content preview: {c.content[:100]!r}")
    except Exception as e:
        print(f"[OxideParser] FAILED: {type(e).__name__}: {e}")


def main() -> int:
    print(f"Python: {sys.version}")
    import office_oxide
    import pdf_oxide
    print(f"office_oxide: {office_oxide.version()}")
    print(f"pdf_oxide:    {pdf_oxide.VERSION if hasattr(pdf_oxide, 'VERSION') else 'unknown'}")
    print(f"workdir:      {TMPDIR}")

    # 生成测试文件
    files: dict[str, Path] = {}

    docx = TMPDIR / "sample.docx"
    make_docx(docx)
    files["DOCX"] = docx

    try:
        xlsx = TMPDIR / "sample.xlsx"
        make_xlsx(xlsx)
        files["XLSX"] = xlsx
    except Exception as e:
        print(f"[WARN] XlsxWriter failed: {e}")

    try:
        pptx = TMPDIR / "sample.pptx"
        make_pptx(pptx)
        files["PPTX"] = pptx
    except Exception as e:
        print(f"[WARN] PptxWriter failed: {e}")

    # 逐个测试
    for name, path in files.items():
        test_parse(name, path)

    print("\n[OK] 测试结束, 临时文件保留在", TMPDIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
