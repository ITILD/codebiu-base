"""doc_parse Skill 实现: 包装 DocumentParseService 产出双产物(实现薄, CA-04 唯一实现体)

impl 契约: run(input, ctx, caps, progress) -> dict —— inline/queued/对话/页面共用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型注解用, 运行期不导入(避免注册链循环)
    from module_agent.service.skill_runtime import (
        CapabilityResolution,
        ProgressFn,
        SkillContext,
    )

logger = logging.getLogger(__name__)


async def run(
    skill_input: dict,
    ctx: SkillContext,
    caps: CapabilityResolution,
    progress: ProgressFn,
) -> dict:
    """执行文档解析: 引擎路由由 office 注册表决策, 视觉/OCR 模型按 ctx.user_id 解析

    :param skill_input: {file_path, filename?, document_id?, options?{ocr}, size_hint?}
    :param caps: 能力解析结果(ocr 缺失时 degraded, 扫描件增强被跳过)
    """
    from module_office.dependencies.document_parse import get_document_parse_service
    from module_office.service.document_parse import DocumentParseService

    file_path = Path(str(skill_input["file_path"]))
    if not file_path.is_file():
        raise ValueError(f"文件不存在: {file_path}")
    filename = str(skill_input.get("filename") or file_path.name)

    await progress(10, f"开始解析 {filename}")
    service: DocumentParseService = get_document_parse_service()
    result = await service.parse(file_path, user_id=ctx.user_id)
    await progress(80, "解析完成, 组装双产物")

    chunks = result.chunks or []
    blocks: list[dict] = []
    markdown_parts: list[str] = []
    for idx, chunk in enumerate(chunks):
        content = chunk.content or ""
        markdown_parts.append(content)
        blocks.append(
            {
                "index": idx,
                "content": content,
                "content_type": getattr(chunk.content_type, "value", str(chunk.content_type)),
                "page": chunk.position.page if chunk.position else None,
                "heading_level": chunk.position.heading_level if chunk.position else None,
                "bbox": chunk.position.bbox if chunk.position else None,
                "metadata": chunk.metadata or {},
            }
        )

    ocr_available = caps.optional.get("ocr", {}).get("available", False)
    degraded = caps.degraded
    warnings: list[str] = []
    if "ocr" in caps.missing_optional:
        warnings.append("OCR 能力未配置: 扫描件/图片内容增强被跳过(产物已标记 degraded)")

    meta = {
        "parser": result.engine,
        "attempts": [a.model_dump() for a in result.attempts],
        "ocr_available": ocr_available,
        "degraded": degraded,
        "warnings": warnings,
        "block_count": len(blocks),
    }
    if skill_input.get("document_id"):
        meta["document_id"] = skill_input["document_id"]
    await progress(100, f"解析完成: {len(blocks)} 个结构块(引擎 {result.engine})")
    return {
        "markdown": "\n".join(markdown_parts),
        "blocks": blocks,
        "meta": meta,
    }
