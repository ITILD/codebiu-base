"""内置只读技能(REQ-013): 网络搜索 / 图片OCR / 文件检索 / 知识库问答

执行函数统一返回文本(回填 ToolMessage 供 LLM 继续), 异常由执行循环捕获降级,
技能自身只做格式化不做重试。
"""

import logging

import httpx
from pydantic import BaseModel, Field

from common.utils.db.schema.pagination import PaginationParams
from module_ai.dependencies.ocr import get_ocr_service
from module_file.service.filesystem import FileService
from module_rag.do.project_document_chunk import SearchRequest
from module_rag.service.project_document_chunk import ProjectDocumentChunkService
from module_websearch.service.websearch import WebSearchService
from module_websearch.utils.websearch.do.websearch import SearchRequest as WSSearchRequest

from module_agent.skills.registry import SkillCapability, SkillContext, SkillDef, register_skill

logger = logging.getLogger(__name__)

# 单图片下载大小上限(15MB, 与 rag 临时文件上限对齐)
_OCR_MAX_BYTES = 15 * 1024 * 1024
# 单个知识片段注入工具结果的字符上限(超出截断, 防超长上下文)
_CHUNK_MAX_CHARS = 800


class WebSearchArgs(BaseModel):
    """网络搜索参数"""

    query: str = Field(..., min_length=1, max_length=500, description="搜索关键词或问题")
    limit: int = Field(default=5, ge=1, le=10, description="返回条数")


async def _web_search(args: WebSearchArgs, ctx: SkillContext) -> str:
    """网络搜索(走已配置引擎, 引擎未配置时由执行循环捕获报错)"""
    resp = await WebSearchService().search(
        WSSearchRequest(query=args.query, limit=args.limit)
    )
    if not resp.results:
        return "未搜索到相关结果"
    lines = [f"网络搜索到 {resp.total} 条结果:"]
    for idx, item in enumerate(resp.results, start=1):
        desc = (item.description or "").replace("\n", " ")[:200]
        lines.append(f"{idx}. [{item.source or item.engine.value}] {item.title}")
        lines.append(f"   摘要: {desc}")
        lines.append(f"   链接: {item.url}")
    return "\n".join(lines)


class OcrImageArgs(BaseModel):
    """图片OCR参数"""

    image_url: str = Field(..., min_length=1, description="图片 URL(http/https)")


async def _ocr_image(args: OcrImageArgs, ctx: SkillContext) -> str:
    """下载图片并 OCR 识别(用户绑定/全局默认 OCR 模型)"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(args.image_url)
        resp.raise_for_status()
        if len(resp.content) > _OCR_MAX_BYTES:
            return f"图片过大(超过 {_OCR_MAX_BYTES // 1024 // 1024}MB), 已跳过识别"
    # cv2 为重依赖, 与 OCR 引擎同惯例延迟导入
    import cv2
    import numpy as np

    image_cv = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)
    if image_cv is None:
        return "无法解析该图片(格式不支持或已损坏)"
    result = await get_ocr_service().recognize(image_cv, user_id=ctx.user_id)
    texts = [it.get("text", "") for it in (result.get("results") or [])]
    content = "\n".join(t for t in texts if t)
    return content or "未识别到文字"


class FileSearchArgs(BaseModel):
    """文件检索参数"""

    keyword: str = Field(..., min_length=1, max_length=200, description="文件名或路径关键词")
    size: int = Field(default=20, ge=1, le=50, description="返回条数")


async def _file_search(args: FileSearchArgs, ctx: SkillContext) -> str:
    """全树模糊搜索文件/目录(名称或逻辑路径匹配)"""
    page = await FileService().search(
        args.keyword, PaginationParams(page=1, size=args.size)
    )
    if not page.items:
        return "未找到相关文件"
    lines = [f"检索到 {page.total} 条文件/目录(展示前 {len(page.items)} 条):"]
    for idx, entry in enumerate(page.items, start=1):
        kind = "目录" if getattr(entry, "is_dir", False) else "文件"
        lines.append(f"{idx}. [{kind}] {getattr(entry, 'name', '')} ({getattr(entry, 'logical_path', '')})")
    return "\n".join(lines)


class RagQaArgs(BaseModel):
    """知识库检索参数"""

    query: str = Field(..., min_length=1, max_length=2000, description="检索问题或关键词")
    project_ids: list[str] = Field(
        default_factory=list, description="知识库ID列表(空则使用助手默认知识库)"
    )


async def _rag_qa(args: RagQaArgs, ctx: SkillContext) -> str:
    """知识库向量检索(按用户可用模型向量化, 项目可见性由检索服务校验)"""
    project_ids = args.project_ids or ctx.default_project_ids
    if not project_ids:
        return "未指定知识库: 请在调用参数中提供 project_ids, 或为助手配置默认知识库"
    chunks = await ProjectDocumentChunkService().search(
        SearchRequest(
            query_content=args.query,
            keyword_query=args.query,
            project_ids=project_ids,
            limit=8,
        ),
        ctx.user_id,
    )
    if not chunks:
        return "知识库中未检索到相关内容"
    lines = [f"知识库检索到 {len(chunks)} 条相关片段:"]
    for idx, chunk in enumerate(chunks, start=1):
        score = getattr(chunk, "score", None)
        score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
        source = getattr(chunk, "source", "") or "未知来源"
        content = (getattr(chunk, "content", "") or "").replace("\n", " ")
        content = content[:_CHUNK_MAX_CHARS] + ("…" if len(content) > _CHUNK_MAX_CHARS else "")
        lines.append(f"{idx}. [{source}] (相关度 {score_text})\n   {content}")
    return "\n".join(lines)


# ── 注册内置只读技能(导入即生效) ──
register_skill(
    SkillDef(
        name="web_search",
        display_name="网络搜索",
        description="联网搜索引擎查询最新信息。适合回答时效性问题、技术资料查找等。",
        capability=SkillCapability.READ,
        args_model=WebSearchArgs,
        func=_web_search,
    )
)
register_skill(
    SkillDef(
        name="ocr_image",
        display_name="图片文字识别",
        description="下载指定 URL 的图片并识别其中的文字(OCR)。适合读取截图、扫描件中的文字。",
        capability=SkillCapability.READ,
        args_model=OcrImageArgs,
        func=_ocr_image,
    )
)
register_skill(
    SkillDef(
        name="file_search",
        display_name="文件检索",
        description="按关键词模糊搜索文件系统中的文件与目录(名称/路径匹配)。适合帮用户定位文件位置。",
        capability=SkillCapability.READ,
        args_model=FileSearchArgs,
        func=_file_search,
    )
)
register_skill(
    SkillDef(
        name="rag_qa",
        display_name="知识库问答",
        description="从指定知识库(项目)中检索相关文档片段。适合回答知识库内文档相关问题。",
        capability=SkillCapability.READ,
        args_model=RagQaArgs,
        func=_rag_qa,
    )
)
