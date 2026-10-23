"""知识库模块 project_document_chunk 业务逻辑层"""

from module_rag.dao.project_document_chunk import ProjectDocumentChunkDao
from module_rag.do.project_document_chunk import (
    SearchRequest,
    ProjectDocumentChunkSearchResponse,
)
from module_ai.utils.llm.types import ModelType
from common.utils.fastapi_ex.exceptions import NotFoundError
from module_rag.service.user_model import UserModelService
from module_ai.service.llm import LLMService
import asyncio
import logging
logger = logging.getLogger(__name__)


class ProjectDocumentChunkService:
    """项目文档数据向量服务对象"""

    def __init__(
        self,
        project_document_chunk_dao: ProjectDocumentChunkDao | None = None,
        user_model_service: UserModelService | None = None,
    ):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.project_document_chunk_dao = (
            project_document_chunk_dao or ProjectDocumentChunkDao()
        )
        self.user_model_service = user_model_service or UserModelService()

    async def search(
        self, request: SearchRequest, user_id: str
    ) -> list[ProjectDocumentChunkSearchResponse]:
        """搜索文档"""
        # 获取模型实例并将查询文本转向量
        embedding_llm = await self.user_model_service.get_llm_by_user_id(
            user_id, False, ModelType.EMBEDDINGS
        )
        if embedding_llm is None:
            # 明确报错: 上游知识检索节点会捕获并记录, 前端过程区块可见"未检索到相关片段"的原因
            raise ValueError("无可用向量化模型, 请在设置中绑定或由管理员配置默认向量化模型")
        try:
            query_vector = await embedding_llm.aembed_query(request.query_content)
            if not query_vector:
                raise ValueError("向量化模型返回空结果")
        except Exception as e:
            logger.warning(f"查询文本向量化失败: {e}")
            # 根因附在消息里(如 Connection error), 检索节点会将原因透传到前端过程区块
            raise ValueError(f"文本向量化失败: {e}") from e

        # 向量维度漂移防护: 向量表是历史模型建的(维度不一致时 Milvus 直接报
        # "vector dimension mismatch" 原始异常), 检索前先校验并自动修复/明确提示
        await self._ensure_table_dim(len(query_vector))

        # 多路并行召回: 向量路(语义) + 关键词路(标量包含匹配, keyword_query 非空时)
        keyword_query = (request.keyword_query or "").strip()
        vector_task = self.project_document_chunk_dao.search(
            query_vector=query_vector,
            project_ids=request.project_ids,
            limit=request.limit,
        )
        keyword_task = (
            self.project_document_chunk_dao.search_by_keyword(
                request.project_ids, keyword_query, limit=request.limit
            )
            if keyword_query
            else None
        )
        if keyword_task:
            vector_hits, keyword_hits = await asyncio.gather(
                vector_task, keyword_task
            )
        else:
            vector_hits, keyword_hits = await vector_task, []

        # 两路合并去重(同块以向量路优先, 其相似度分数可比), 关键词路补召回向量未覆盖块
        merged: dict[str, ProjectDocumentChunkSearchResponse] = {}
        for hit in vector_hits + keyword_hits:
            if hit.id not in merged:
                merged[hit.id] = hit
        results = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        logger.info(
            f"[Search] 多路召回完成 | 向量={len(vector_hits)} 关键词={len(keyword_hits)} "
            f"去重合并={len(results)} enable_rerank={request.enable_rerank} "
            f"score_threshold={request.score_threshold}"
        )

        # rerank: 仅当显式开启(深度思考)时执行精排,并按 score_threshold 过滤低分结果
        if request.enable_rerank:
            rerank_llm = await self.user_model_service.get_llm_by_user_id(
                user_id, False, ModelType.RERANK
            )
            if rerank_llm:
                logger.info(f"[Search] 深度思考已开启, 启动 Rerank 精排 | 候选数={len(results)}")
                results = await self.rerank_candidates(
                    rerank_llm,
                    request.query_content,
                    results,
                    request.rerank_limit,
                    request.score_threshold,
                )
                logger.info(f"[Search] Rerank 精排完成 | 最终返回={len(results)} 条")
            else:
                logger.warning(f"[Search] 深度思考已开启但用户未绑定 Rerank 模型, 跳过精排")
        else:
            logger.info(f"[Search] 深度思考未开启, 跳过 Rerank 精排")

        return results

    async def _ensure_table_dim(self, current_dim: int) -> None:
        """向量表维度与当前向量化模型一致性校验(检索前/写入前防护)

        - 一致: 直接返回(常态路径, 仅一次 describe 开销)
        - 不一致且向量表有数据: 抛出可读错误, 提示执行"重新向量化"(勿静默重建丢数据)
        - 不一致且向量表为空: 直接重建为当前维度(自愈; 失败文档可重新解析恢复)
        """
        from module_rag.do.project_document_chunk import ProjectDocumentChunk
        from common.config.db import db_vector

        table_name = "projectdocumentchunk"  # 与 ProjectDocumentChunkDao 一致: 类名小写
        old_dim = await db_vector.get_vector_dim(table_name, "embedding")
        if old_dim is None or old_dim == current_dim:
            return

        # 仅当向量表已有数据才需要保护(迁移走重向量化), 空表重建零风险
        probe = await db_vector.query_by_filter(
            table_name, "sort >= 0", output_fields=["id"], limit=1
        )
        if probe:
            raise ValueError(
                f"向量表维度({old_dim})与当前向量化模型维度({current_dim})不一致, "
                f"请先执行全库重新向量化"
            )

        # 空表: 重建自愈, 后续按当前维度写入
        logger.warning(f"向量表维度漂移 {old_dim} -> {current_dim} 且向量表为空, 自动重建向量表")
        await db_vector.drop_table(table_name)
        await db_vector.create_table(ProjectDocumentChunk, {"embedding": current_dim})

    async def rerank_candidates(
        self,
        rerank_llm,
        query: str,
        candidates: list,
        top_n: int,
        score_threshold: float = 0.5
    ) -> list:
        """
        对候选对象列表做 Rerank 精排(公开方法, 供知识库精排与 RAG 联网合并精排共用)
        :param rerank_llm: Rerank 模型实例
        :param query: 用户查询文本
        :param candidates: 候选对象列表(需含 content 属性/字段, 如知识片段或联网引用)
        :param top_n: 最终返回条数
        :param score_threshold: 归一化后 0~1 相关性阈值, 低于该值的结果被过滤
        :return: 精排后的原对象列表(按相关度降序, 高精度分数已回写对象 score 字段)
        """
        doc_list = [
            {"content": getattr(res, "content", "") or "", "node": res}
            for res in candidates
        ]

        logger.info(
            f"[Rerank] 准备精排 | query='{query[:50]}' | 候选={len(candidates)} | "
            f"top_n={top_n} score_threshold={score_threshold}"
        )

        try:
            reranked_results = await rerank_llm.arerank_dict_list(
                query=query,
                doc_list=doc_list,
                sort_key="content",
                top_n=top_n,
                score_threshold=score_threshold  # 可以根据需要调整阈值
            )
            logger.info(
                f"[Rerank] 精排结束 | 精排前={len(candidates)} 精排后={len(reranked_results)} | " 
            )
            # return [item["node"] for item in reranked_results]
            final_results = []
            for item in reranked_results:
                obj = item["node"]
                
                # 顺手将 Rerank 的高精度分数，更新到原始对象的 score 字段
                if hasattr(obj, "score"):
                    obj.score = item["relevance_score"]
                final_results.append(obj)
            return final_results

        except Exception as e:
            logger.warning(f"Rerank 重排序失败，降级返回向量检索结果: {e}")
            return candidates[:top_n]

    async def vector_delete_by_document_id(self, document_id: str):
        """根据文档ID删除向量"""
        await self.project_document_chunk_dao.vector_delete_by_document_id(document_id)

    async def vector_delete_by_project_id(self, project_id: str):
        """根据项目ID删除向量"""
        await self.project_document_chunk_dao.vector_delete_by_project_id(project_id)

    # ################ 全库重向量化(系统管理员运维操作, Celery 任务与直跑接口共用) ################

    async def revectorize_all(
        self,
        model_id: str | None = None,
        progress_cb=None,
    ) -> dict:
        """
        以目标 embedding 模型重算向量库中所有文档 chunk 向量
        (功能服务层实现: Celery 任务与 controller 直跑接口共用, 保证"零逻辑重复")

        实现要点(LanceDB):
        - 按文档逐个读出元数据行并重算向量(收集阶段原表不动, 中途失败无副作用)
        - 全部收集完成后重建向量表并写回(维度变更无需特殊分支, 天然支持换模型)
        - 原 chunk id 保留, 分块与文档的引用关系不变

        :param model_id: 目标向量化模型配置ID(None 时使用当前生效的默认公共 embedding 模型)
        :param progress_cb: 可选异步进度回调 (processed_docs, total_docs, chunks, model_label, dim_changed);
                            Celery 任务传入用于双写进度, 直跑接口传 None
        :return: 统计结果 {total_chunks, processed_chunks, documents, model, dim_changed}
        :raises ValueError: 模型不存在/加载失败/无生效默认模型
        """
        from module_ai.dao.model_config import ModelConfigDao
        from module_ai.service.llm import LLMService
        from module_rag.dao.project_document import ProjectDocumentDao
        from module_rag.do.project_document_chunk import ProjectDocumentChunk
        from common.config.db import db_vector

        # 1. 确定目标 embedding 模型
        if not model_id:
            fallback = await ModelConfigDao().get_default_by_type(
                ModelType.EMBEDDINGS.value, active_only=True
            )
            if fallback is None:
                raise ValueError("没有生效的默认公共向量化模型, 请先在模型配置中设置")
            model_id = fallback.id
        model_config = await ModelConfigDao().get(model_id)
        if model_config is None:
            raise NotFoundError(f"模型配置不存在: {model_id}")
        embeddings_llm = await LLMService().get_llm(model_id, False)
        if embeddings_llm is None:
            raise ValueError(f"加载向量化模型失败: {model_config.model}")
        model_label = model_config.display_name or model_config.model

        # 2. 探测新模型向量维度
        probe = await embeddings_llm.aembed_query("维度探测")
        if not probe:
            raise ValueError("向量化模型返回空结果, 无法探测维度")
        new_dim = len(probe)

        # 3. 检查向量表与旧维度
        table_name = "projectdocumentchunk"  # 与 ProjectDocumentChunkDao 一致: 类名小写
        old_dim = await db_vector.get_vector_dim(table_name, "embedding")
        if old_dim is None:
            logger.info("向量表不存在, 无需重向量化")
            return {"total_chunks": 0, "processed_chunks": 0, "documents": 0,
                    "model": model_label, "dim_changed": False}
        dim_changed = old_dim != new_dim
        if dim_changed:
            logger.info(f"向量维度变更 {old_dim} -> {new_dim}, 将重建向量表后全量写入")

        # 4. 遍历文档收集行(原表不动), 收集完统一并发向量化(逐文档串行 embed 是耗时大头)
        document_ids = await ProjectDocumentDao().list_all_ids()
        total_documents = len(document_ids)
        processed_chunks = 0
        pending_rows: list[dict] = []
        meta_fields = [
            f for f in ProjectDocumentChunk.model_fields.keys() if f != "embedding"
        ]
        # 逐文档串行查询在文档数大时往返显著, 按批并发拉取(每批内 gather 重叠网络 IO)
        fetch_batch = 50
        for start in range(0, total_documents, fetch_batch):
            batch_ids = document_ids[start : start + fetch_batch]
            results = await asyncio.gather(
                *(
                    db_vector.query_by_filter(
                        table_name, f'document_id == "{doc_id}"', output_fields=meta_fields
                    )
                    for doc_id in batch_ids
                )
            )
            for rows in results:
                if rows:
                    pending_rows.extend(rows)
                    processed_chunks += len(rows)
            # 进度回调(任务侧双写 task_queue 表与结果后端; 直跑为 None)
            if progress_cb is not None:
                try:
                    await progress_cb(
                        min(start + fetch_batch, total_documents),
                        total_documents,
                        processed_chunks,
                        model_label,
                        dim_changed,
                    )
                except Exception as e:
                    logger.debug(f"重向量化进度回调失败(忽略): {e}")

        # 统一并发向量化(分批+并发, 网络 IO 重叠; 顺序与 pending_rows 对齐)
        if pending_rows:
            from module_ai.utils.llm.embed import embed_documents_concurrent

            texts = [r.get("content") or "" for r in pending_rows]
            vectors = await embed_documents_concurrent(embeddings_llm, texts)
            for row, vec in zip(pending_rows, vectors):
                row["embedding"] = vec

        # 5. 重建向量表并写回(drop 幂等: 表不存在时静默跳过)
        await db_vector.drop_table(table_name)
        await db_vector.create_table(ProjectDocumentChunk, {"embedding": new_dim})
        batch: list[ProjectDocumentChunk] = []
        for row in pending_rows:
            batch.append(ProjectDocumentChunk(
                id=row.get("id"),
                sort=row.get("sort", 0),
                document_id=row.get("document_id"),
                project_id=row.get("project_id"),
                content=row.get("content") or "",
                source=row.get("source") or "",
                content_types=row.get("content_types") or [],
                position=row.get("position"),
                metadata=row.get("metadata"),
                embedding=row.get("embedding"),
            ))
            if len(batch) >= 500:
                await db_vector.add(batch)
                batch = []
        if batch:
            await db_vector.add(batch)

        logger.info(
            f"全库重向量化完成 model={model_label} dim {old_dim}->{new_dim} "
            f"documents={total_documents} chunks={processed_chunks}"
        )
        return {"total_chunks": processed_chunks, "processed_chunks": processed_chunks,
                "documents": total_documents, "model": model_label, "dim_changed": dim_changed}
