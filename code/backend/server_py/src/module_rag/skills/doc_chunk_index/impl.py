"""doc_chunk_index Skill 实现: 策略识别(可降级) → 重分块 → 向量化/降级入库 → 状态回写

impl 契约: run(input, ctx, caps, progress) -> dict —— 三条入口共用同一实现(CA-04)。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型注解用, 运行期不导入(避免注册链循环)
    from module_agent.service.skill_runtime import (
        CapabilityResolution,
        ProgressFn,
        SkillContext,
    )

logger = logging.getLogger(__name__)

# 降级路线(零向量入库)的占位维度: 表不存在时按此建表;
# 配置 embeddings 后需执行全库重向量化恢复语义检索
_PLACEHOLDER_DIM = 1024


async def run(
    skill_input: dict,
    ctx: SkillContext,
    caps: CapabilityResolution,
    progress: ProgressFn,
) -> dict:
    """执行分块入库

    :param skill_input: {document_id, blocks(doc_parse 产物), markdown?, chunk_config?, size_hint?}
    :param caps: 能力组解析结果(首选组=embeddings 完整路线; 降级组=store:bm25 零向量入库)
    """
    from module_ai.utils.llm.types import ModelType
    from module_office.service.document_chunk import DocumentChunkService
    from module_office.utils.document_chunk.do.chunk import (
        ChunkConfig,
        ChunkStrategyEnum,
    )
    from module_office.utils.file_parse.do.chunk import Chunk, ContentType, Position
    from module_rag.dao.project_document import ProjectDocumentDao
    from module_rag.do.project_document import ParseStatus, ProjectDocumentUpdate
    from module_rag.do.project_document_chunk import ProjectDocumentChunk
    from module_rag.service.project_document_chunk import ProjectDocumentChunkService
    from module_rag.service.user_model import UserModelService

    document_id = str(skill_input["document_id"])
    blocks = skill_input.get("blocks") or []
    if not blocks:
        raise ValueError("blocks 为空: 无可入库的解析产物(应在上游跳过而非调入库)")

    document_dao = ProjectDocumentDao()
    document = await document_dao.get(document_id)
    if document is None:
        raise ValueError(f"文档不存在: {document_id}")
    # 资源授权范围(仅过滤用, 不可扩大, CA-08): 调用方显式限定 project_ids 时校验归属
    if ctx.project_ids and document.project_id not in ctx.project_ids:
        raise PermissionError(
            f"文档 {document_id} 不在授权项目范围内(project_ids={ctx.project_ids})"
        )

    # 入库进行中(供前端轮询)
    await document_dao.update(
        document_id, ProjectDocumentUpdate(parse_status=ParseStatus.PARSING)
    )

    async def _fail(error_message: str) -> None:
        try:
            await document_dao.update(
                document_id,
                ProjectDocumentUpdate(
                    parse_status=ParseStatus.FAILED, error_message=error_message[:1000]
                ),
            )
        except Exception as e:  # 状态回写失败不掩盖原始异常
            logger.warning("回写文档失败状态异常 document_id=%s: %s", document_id, e)

    try:
        # ── 1. 分块策略识别(optional chat, 缺失降级 general) ──
        await progress(10, "分块策略识别")
        strategy = ChunkStrategyEnum.GENERAL
        strategy_by_model = False
        if caps.optional.get("chat", {}).get("available"):
            chat_llm = await UserModelService().get_llm_by_user_id(ctx.user_id, False)
            if chat_llm is not None:
                sample = str(skill_input.get("markdown") or "")[:4000] or "\n".join(
                    str(b.get("content") or "") for b in blocks[:10]
                )
                recommendation = await DocumentChunkService().detect_strategy(
                    document.name, sample, chat_llm
                )
                strategy = recommendation.strategy
                strategy_by_model = True
        warnings: list[str] = []
        if not strategy_by_model:
            warnings.append("策略识别能力不可用, 已降级默认策略 general")

        # ── 2. 重分块(ragflow 合并为纯 CPU 同步计算, 挪线程避免阻塞循环) ──
        await progress(25, f"按策略 {strategy.value} 重分块")
        config_kwargs = skill_input.get("chunk_config") or {}
        chunk_config = ChunkConfig(**config_kwargs) if config_kwargs else ChunkConfig()
        chunks = [
            Chunk(
                content=str(b.get("content") or ""),
                content_type=ContentType(b.get("content_type") or "text"),
                position=Position(
                    page=b.get("page"),
                    heading_level=b.get("heading_level"),
                    bbox=b.get("bbox"),
                ),
                metadata={str(k): str(v) for k, v in (b.get("metadata") or {}).items()},
            )
            for b in blocks
        ]
        chunked_items = await asyncio.to_thread(
            DocumentChunkService().chunk,
            chunks=chunks,
            strategy=strategy,
            config=chunk_config,
            engine="ragflow",
        )
        if not chunked_items:
            await document_dao.update(
                document_id,
                ProjectDocumentUpdate(parse_status=ParseStatus.COMPLETED, chunk_count=0),
            )
            await progress(100, "未切分出内容块, 无需入库")
            return {
                "document_id": document_id,
                "chunk_count": 0,
                "strategy": strategy.value,
                "route": "none",
                "meta": {"degraded": caps.degraded, "warnings": warnings},
            }

        # ── 3. 入库路线(能力组: embeddings 完整 / store:bm25 降级零向量) ──
        chunk_service = ProjectDocumentChunkService()
        insert_data: list[ProjectDocumentChunk] = []
        for idx, item in enumerate(chunked_items):
            insert_data.append(
                ProjectDocumentChunk(
                    sort=idx,
                    document_id=document_id,
                    project_id=document.project_id,
                    content=item.content[:8192],
                    source=item.source or document.name,
                    content_types=item.content_types,
                    position=item.position,
                    metadata=(
                        json.dumps(item.metadata, ensure_ascii=False)
                        if item.metadata else None
                    ),
                )
            )

        from common.config.db import db_vector

        if caps.group_satisfies("embeddings"):
            # 完整路线: 并发向量化 → 维度防护 → 删旧写新
            await progress(45, f"向量化 {len(chunked_items)} 个内容块")
            from module_ai.utils.llm.embed import embed_documents_concurrent

            embedding_llm = await UserModelService().get_llm_by_user_id(
                ctx.user_id, False, ModelType.EMBEDDINGS
            )
            if embedding_llm is None:
                raise ValueError(
                    "向量化模型实例加载失败(embeddings 能力解析通过但实例不可用), 请检查模型配置"
                )
            texts = [item.content[:8192] for item in chunked_items]
            embeddings = await embed_documents_concurrent(embedding_llm, texts)
            await chunk_service._ensure_table_dim(len(embeddings[0]))
            for row, emb in zip(insert_data, embeddings):
                row.embedding = emb
            route, vector_dim = "vector", len(embeddings[0])
        else:
            # 降级路线(store:bm25, W-6): 零模型环境零向量入库, 检索走关键词全文索引;
            # 零向量在余弦度量下相似度恒最低, 不会污染语义检索排序
            await progress(45, f"零向量降级入库 {len(chunked_items)} 个内容块(关键词检索路线)")
            table_name = "projectdocumentchunk"
            dim = await db_vector.get_vector_dim(table_name, "embedding")
            if dim is None:
                await db_vector.create_table(
                    ProjectDocumentChunk, {"embedding": _PLACEHOLDER_DIM}
                )
                dim = _PLACEHOLDER_DIM
                warnings.append(
                    f"向量表按占位维度 {_PLACEHOLDER_DIM} 新建; 配置向量化模型后请执行全库重向量化"
                )
            for row in insert_data:
                row.embedding = [0.0] * dim
            route, vector_dim = "keyword_only", dim
            warnings.append("embeddings 能力不可用: 已按 BM25-only 降级路线入库(degraded)")

        await progress(75, "写入向量库")
        await chunk_service.vector_delete_by_document_id(document_id)
        await db_vector.add(insert_data)

        # parse_steps 摘要回写(与既有 reparse 链路口径兼容, 供文档详情展示;
        # 完整调用级观测以 skill_invocation 为准, 两级观测并存)
        parse_steps = {
            "chunk_strategy": {"status": "done", "strategy": strategy.value, "by_model": strategy_by_model},
            "chunk": {"status": "done", "chunk_count": len(insert_data)},
            "embed": {"status": "done", "route": route, "vector_dim": vector_dim},
            "store": {"status": "done", "collection": "projectdocumentchunk"},
        }
        await document_dao.update(
            document_id,
            ProjectDocumentUpdate(
                parse_status=ParseStatus.COMPLETED,
                chunk_count=len(insert_data),
                parse_steps=parse_steps,
            ),
        )
        await progress(100, f"入库完成: {len(insert_data)} 块(路线 {route})")
        return {
            "document_id": document_id,
            "chunk_count": len(insert_data),
            "strategy": strategy.value,
            "route": route,
            "meta": {
                "degraded": caps.degraded or route == "keyword_only",
                "vector_dim": vector_dim,
                "warnings": warnings,
            },
        }
    except Exception as e:
        logger.error("doc_chunk_index 失败 document_id=%s: %s", document_id, e, exc_info=True)
        await _fail(f"{type(e).__name__}: {e}")
        raise
