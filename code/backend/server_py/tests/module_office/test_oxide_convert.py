"""Oxide 转格式/提取 独立测试(不依赖 DB, 直接 ``uv run python tests/test_oxide_convert.py``)

覆盖:
1. 提取: temp_source/test 真实样例(docx/xlsx/图片类pdf/文本类pdf) + 程序生成的
   pptx 样本 → markdown / JSON 文档结构(IR) / text 各形态
2. 转格式: PDF → docx/pptx/xlsx(pdf_oxide 原生); Office → docx/xlsx/pptx
   (office_oxide save_as, 失败降级 markdown 中转); Markdown → docx/xlsx/pptx
3. 产物回读校验(转换结果必须能被再次解析)

结论性输出: 每种格式对 markdown/JSON 结构的支持情况。
旧版二进制样本(.doc/.xls/.ppt)仓库缺失且无 LibreOffice, 无法本地生成,
解析支持以 office_oxide 声明为准(README/pypi), 此处不覆盖。
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from office_oxide import PptxWriter, XlsxWriter

from module_office.utils.file_parse.oxide import (
    OxideConvertError,
    convert,
    extract_output,
    markdown_to_office,
)

SAMPLE_DIR = ROOT / "temp_source" / "test"
OUT_DIR = Path(tempfile.mkdtemp(prefix="oxide_convert_test_"))

results: list[tuple[str, str, str]] = []  # (用例, 结论, 备注)


def make_pptx(path: Path) -> None:
    writer = PptxWriter()
    idx = writer.add_slide()
    writer.set_slide_title(idx, "Oxide 转格式测试")
    writer.add_slide_text(idx, "第一页要点: pdf_oxide PDF→Office")
    writer.add_slide_text(idx, "第二要点: office_oxide save_as / create_from_markdown")
    writer.save(str(path))


def make_xlsx(path: Path) -> None:
    writer = XlsxWriter()
    idx = writer.add_sheet("测试表")
    writer.set_cell(idx, 0, 0, "名称")
    writer.set_cell(idx, 0, 1, "数量")
    writer.set_cell(idx, 1, 0, "样例A")
    writer.set_cell(idx, 1, 1, 3)
    writer.save(str(path))


def check_extract(label: str, file: Path, out: str) -> str | dict:
    result = asyncio.run(extract_output(file, out))
    content = result["content"]
    size = len(content) if isinstance(content, str) else len(json.dumps(content, ensure_ascii=False))
    results.append((f"提取 {label} → {out}", "OK", f"{size} 字符"))
    return content


def check_convert(label: str, src: Path, target: str) -> Path:
    data, fmt, strategy = convert(src, target)
    out = OUT_DIR / f"{src.stem}{target}"
    out.write_bytes(data)
    # 回读校验
    if fmt == "pdf":
        from pdf_oxide import PdfDocument

        with PdfDocument(str(out)) as doc:
            assert len(doc) >= 1, "转换产物 0 页"
            read_back = doc.to_plain_text_all()[:50]
    else:
        from office_oxide import Document

        with Document.open(str(out)) as doc:
            assert doc.format == fmt, f"产物格式 {doc.format} != {fmt}"
            read_back = (doc.plain_text() or "")[:50]
    results.append((f"转格式 {label} → {fmt}", "OK", f"{strategy}; 回读: {read_back!r}"))
    return out


def check_fail(label: str, src: Path, target: str) -> None:
    try:
        convert(src, target)
    except OxideConvertError as exc:
        results.append((f"转格式 {label} → {target}", "预期失败", str(exc)))
    else:
        results.append((f"转格式 {label} → {target}", "意外成功", "应抛 OxideConvertError"))


def check_markdown_create(target: str) -> Path:
    md = "# 测试文档\n\n这是 **create_from_markdown** 生成的段落。\n\n- 要点一\n- 要点二\n"
    out = OUT_DIR / f"from_md{target}"
    strategy = markdown_to_office(md, target, out)
    from office_oxide import Document

    with Document.open(str(out)) as doc:
        text = (doc.plain_text() or "")[:50]
    results.append((f"Markdown 生成 {target}", "OK", f"{strategy}; 回读: {text!r}"))
    return out


def main() -> int:
    print(f"输出目录: {OUT_DIR}\n")

    # ---- 收集样本(真实样例 + 生成 pptx/xlsx 兜底) ----
    samples: dict[str, Path] = {}
    for f in sorted(SAMPLE_DIR.iterdir()):
        if f.suffix.lower() in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}:
            samples[f.name] = f
    gen_pptx = OUT_DIR / "generated.pptx"
    make_pptx(gen_pptx)
    samples["generated.pptx(生成)"] = gen_pptx

    print("== 样本 ==")
    for name in samples:
        print(f"  {name}")
    print()

    # ---- 1. 提取: markdown / JSON(IR) / text ----
    print("== 提取测试 ==")
    ir_summary: dict[str, str] = {}
    for name, path in samples.items():
        for out in ("markdown", "json", "text"):
            try:
                content = check_extract(name, path, out)
                if out == "json":
                    keys = sorted(content.keys()) if isinstance(content, dict) else []
                    ir_summary[name] = ",".join(keys) or "标量"
                    print(f"  [JSON结构] {name}: keys={keys}")
            except Exception as e:  # noqa: BLE001
                results.append((f"提取 {name} → {out}", "FAIL", f"{type(e).__name__}: {e}"))
    print()

    # ---- 2. 转格式矩阵 ----
    print("== 转格式测试 ==")
    docx = samples.get("docx标准测试.docx")
    xlsx = samples.get("xlsx标准测试.xlsx")
    pdf_text = samples.get("文本类pdf标准测试.pdf")
    pptx = gen_pptx
    # 旧版二进制样本: doc 来自 Apache POI 测试样本(curl 下载, OLE 魔数校验);
    # xls 由 xlwt 生成(uv run --with xlwt)。office_oxide save_as 只读不写旧格式,
    # 但读→新格式转换是原生支持的。
    doc_legacy = samples.get("doc标准测试.doc")
    xls_legacy = samples.get("xls标准测试.xls")

    if pdf_text:
        for t in (".docx", ".pptx", ".xlsx"):
            try:
                check_convert("文本pdf", pdf_text, t)
            except Exception as e:  # noqa: BLE001
                results.append((f"转格式 文本pdf → {t}", "FAIL", f"{type(e).__name__}: {e}"))
    if docx:
        try:
            check_convert("docx", docx, ".xlsx")
        except Exception as e:  # noqa: BLE001
            results.append(("转格式 docx → .xlsx", "FAIL", f"{type(e).__name__}: {e}"))
    if xlsx:
        try:
            check_convert("xlsx", xlsx, ".docx")
        except Exception as e:  # noqa: BLE001
            results.append(("转格式 xlsx → .docx", "FAIL", f"{type(e).__name__}: {e}"))
    try:
        check_convert("pptx", pptx, ".docx")
    except Exception as e:  # noqa: BLE001
        results.append(("转格式 pptx → .docx", "FAIL", f"{type(e).__name__}: {e}"))
    # 旧版二进制 → 新格式(重点用例)
    if doc_legacy:
        try:
            check_convert("doc(旧版)", doc_legacy, ".docx")
        except Exception as e:  # noqa: BLE001
            results.append(("转格式 doc(旧版) → .docx", "FAIL", f"{type(e).__name__}: {e}"))
    else:
        results.append(("转格式 doc(旧版) → .docx", "跳过", "缺少 doc标准测试.doc 样本"))
    if xls_legacy:
        try:
            check_convert("xls(旧版)", xls_legacy, ".xlsx")
        except Exception as e:  # noqa: BLE001
            results.append(("转格式 xls(旧版) → .xlsx", "FAIL", f"{type(e).__name__}: {e}"))
    else:
        results.append(("转格式 xls(旧版) → .xlsx", "跳过", "缺少 xls标准测试.xls 样本"))

    # 反向/不支持方向应明确报错
    if docx:
        check_fail("docx", docx, ".pdf")  # Office→PDF 不支持
    check_fail("同格式", docx or pptx, (docx or pptx).suffix)

    # ---- 3. Markdown 直接生成 ----
    for t in (".docx", ".xlsx", ".pptx"):
        try:
            check_markdown_create(t)
        except Exception as e:  # noqa: BLE001
            results.append((f"Markdown 生成 {t}", "FAIL", f"{type(e).__name__}: {e}"))
    print()

    # ---- 汇总 ----
    print("== 结果汇总 ==")
    width = max(len(r[0]) for r in results)
    fails = 0
    for label, verdict, note in results:
        mark = {"OK": "✓", "FAIL": "✗", "预期失败": "⊘"}.get(verdict, "?")
        if verdict == "FAIL":
            fails += 1
        print(f"  {mark} {label:<{width}}  {verdict}  | {note[:110]}")

    print("\n== 各格式结构支持结论 ==")
    for name, keys in ir_summary.items():
        print(f"  {name}: JSON/IR keys = [{keys}]")

    print(f"\n[{'FAIL' if fails else 'OK'}] 失败 {fails} 项; 产物保留在 {OUT_DIR}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
