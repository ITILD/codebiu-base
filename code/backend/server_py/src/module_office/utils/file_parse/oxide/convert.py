"""Oxide 转格式: pdf/doc/docx/xls/xlsx/ppt/pptx → docx/xlsx/pptx

能力矩阵(office-oxide 0.1.x / pdf-oxide 0.3.x 实测):
- PDF → docx/pptx/xlsx: pdf_oxide 原生 ``to_docx_bytes/to_pptx_bytes/to_xlsx_bytes``
- Office → docx/xlsx/pptx: office_oxide ``save_as``(按目标后缀重写);
  跨格式失败时降级为 markdown 中转 ``create_from_markdown``
- Markdown → docx/xlsx/pptx: office_oxide ``create_from_markdown``

注: 两库均不支持 Office → PDF, 该方向请走 MinerU/LibreOffice 链路。
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 允许的目标格式(转出方向)
TARGET_SUFFIXES = {".docx", ".xlsx", ".pptx"}
# 可读取的源格式
SOURCE_SUFFIXES = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


class OxideConvertError(RuntimeError):
    """转格式失败(不支持的源/目标或底层引擎报错)"""


def _check_suffix(src: Path, target: str) -> tuple[str, str]:
    src_suffix = src.suffix.lower()
    target_suffix = target.lower()
    if not target_suffix.startswith("."):
        target_suffix = f".{target_suffix}"
    if src_suffix not in SOURCE_SUFFIXES:
        raise OxideConvertError(f"不支持的源格式: {src_suffix} (支持: {sorted(SOURCE_SUFFIXES)})")
    if target_suffix not in TARGET_SUFFIXES:
        raise OxideConvertError(f"不支持的目标格式: {target_suffix} (支持: {sorted(TARGET_SUFFIXES)})")
    return src_suffix, target_suffix


def pdf_to_office(src: Path, target: str) -> tuple[bytes, str]:
    """PDF → docx/pptx/xlsx, 返回 (文件字节, 转换策略说明)"""
    _, target_suffix = _check_suffix(src, target)
    from pdf_oxide import PdfDocument

    convert_fn = {
        ".docx": "to_docx_bytes",
        ".pptx": "to_pptx_bytes",
        ".xlsx": "to_xlsx_bytes",
    }[target_suffix]
    with PdfDocument(str(src)) as doc:
        data = getattr(doc, convert_fn)()
    return data, f"pdf_oxide.{convert_fn}"


def markdown_to_office(markdown: str, target: str, out_path: Path) -> str:
    """Markdown → docx/xlsx/pptx, 写入 out_path, 返回策略说明"""
    from office_oxide import create_from_markdown

    _check_suffix(out_path, target)
    create_from_markdown(markdown, out_path.suffix.lstrip("."), str(out_path))
    return "office_oxide.create_from_markdown"


def office_to_office(src: Path, target: str) -> tuple[bytes, str]:
    """Office(doc/docx/xls/xlsx/ppt/pptx) → docx/xlsx/pptx

    优先 office_oxide ``save_as`` 直接重写; 校验产物可重新打开,
    失败则降级 markdown 中转。
    """
    _, target_suffix = _check_suffix(src, target)
    from office_oxide import Document

    with tempfile.TemporaryDirectory(prefix="oxide_convert_") as tmp:
        out = Path(tmp) / f"converted{target_suffix}"
        try:
            with Document.open(str(src)) as doc:
                doc.save_as(str(out))
            data = out.read_bytes()
            # 校验产物可被重新解析, 防止 save_as 未真正转换时产出空壳
            with Document.open(str(out)):
                pass
            return data, "office_oxide.save_as"
        except Exception as exc:  # noqa: BLE001 — 降级 markdown 中转
            logger.info("save_as 转换不可用(%s), 降级 markdown 中转", exc)

        with Document.open(str(src)) as doc:
            md = doc.to_markdown() or doc.plain_text() or ""
        if not md.strip():
            raise OxideConvertError(f"源文档无文本内容, 无法转出 {target_suffix}")
        markdown_to_office(md, target_suffix, out)
        return out.read_bytes(), "office_oxide.save_as→create_from_markdown"


def convert(src: Path, target: str) -> tuple[bytes, str, str]:
    """统一转格式入口

    :param src: 源文件路径(pdf/doc/docx/xls/xlsx/ppt/pptx)
    :param target: 目标后缀(docx/xlsx/pptx, 含或不含点)
    :return: (目标文件字节, 实际格式名, 转换策略说明)
    """
    src_suffix, target_suffix = _check_suffix(src, target)
    if src_suffix == target_suffix:
        raise OxideConvertError(f"源格式与目标格式相同: {src_suffix}")

    if src_suffix == ".pdf":
        data, strategy = pdf_to_office(src, target_suffix)
    else:
        data, strategy = office_to_office(src, target_suffix)
    return data, target_suffix.lstrip("."), strategy
