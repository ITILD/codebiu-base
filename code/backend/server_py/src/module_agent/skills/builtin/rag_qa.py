"""rag_qa Skill(hybrid): 知识库检索(embeddings 必需, rerank 可选)"""

from __future__ import annotations

from typing import TYPE_CHECKING

from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    RetrySpec,
    SkillManifest,
    SkillNature,
)
from module_agent.skills.registry import register_skill

if TYPE_CHECKING:  # 仅类型注解用, 运行期不导入(避免注册链循环)
    from module_agent.service.skill_runtime import (
        CapabilityResolution,
        ProgressFn,
        SkillContext,
    )

# 单个知识片段注入工具结果的字符上限(超出截断, 防超长上下文)
_CHUNK_MAX_CHARS = 800

register_skill(
    SkillManifest(
        namespace="sys",
        key="rag_qa",
        name="知识库问答",
        description="从指定知识库(项目)中检索相关文档片段。适合回答知识库内文档相关问题。",
        category="retrieval",
        nature=SkillNature.HYBRID.value,
        impl_ref="module_agent.skills.builtin.rag_qa:run",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "maxLength": 2000, "description": "检索问题或关键词"},
                "project_ids": {"type": "array", "items": {"type": "string"}, "description": "知识库ID列表(空则用助手默认知识库)"},
                "limit": {"type": "integer", "default": 8, "description": "返回片段数"},
            },
        },
        output_schema={"type": "object", "properties": {"text": {"type": "string"}, "chunks": {"type": "integer"}}},
        required_capabilities=["embeddings"],
        optional_capabilities=["rerank"],
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=60, resource_domain="llm"),
        idempotency=IdempotencySpec(keys=["query", "project_ids"]),
        retry=RetrySpec(max=1),
        side_effects="read",
        agent_callable=True,
    )
)


async def run(
    skill_input: dict,
    ctx: SkillContext,
    caps: CapabilityResolution,
    progress: ProgressFn,
) -> dict:
    """知识库向量检索(按用户可用模型向量化, 项目可见性由检索服务校验)"""
    from module_rag.do.project_document_chunk import SearchRequest
    from module_rag.service.project_document_chunk import ProjectDocumentChunkService

    project_ids = list(skill_input.get("project_ids") or []) or ctx.project_ids
    if not project_ids:
        return {
            "text": "未指定知识库: 请在调用参数中提供 project_ids, 或为助手配置默认知识库",
            "chunks": 0,
        }
    await progress(40, "知识库检索中")
    chunks = await ProjectDocumentChunkService().search(
        SearchRequest(
            query_content=str(skill_input["query"]),
            keyword_query=str(skill_input["query"]),
            project_ids=project_ids,
            limit=int(skill_input.get("limit") or 8),
        ),
        ctx.user_id,
    )
    lines: list[str] = []
    if not chunks:
        lines.append("知识库中未检索到相关内容")
    else:
        lines.append(f"知识库检索到 {len(chunks)} 条相关片段:")
        for idx, chunk in enumerate(chunks, start=1):
            score = getattr(chunk, "score", None)
            score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
            source = getattr(chunk, "source", "") or "未知来源"
            content = (getattr(chunk, "content", "") or "").replace("\n", " ")
            content = content[:_CHUNK_MAX_CHARS] + ("…" if len(content) > _CHUNK_MAX_CHARS else "")
            lines.append(f"{idx}. [{source}] (相关度 {score_text})\n   {content}")
    await progress(100, "检索完成")
    return {"text": "\n".join(lines), "chunks": len(chunks)}
