"""知识库模块 project_document_chunk 数据访问层"""

from module_rag.do.project_document_chunk import (
    ProjectDocumentChunk,
    ProjectDocumentChunkSearchBase,
    ProjectDocumentChunkSearchResponse,
)
import logging

logger = logging.getLogger(__name__)


class ProjectDocumentChunkDao:
    """项目文档分块向量数据访问对象(LanceDB)

    基线说明: 仅保留稠密向量语义检索; 原 Milvus BM25 混合检索
    (AnnSearchRequest/RRFRanker)已随重型依赖裁剪移除。
    """

    def __init__(self):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.collection_name = ProjectDocumentChunk.__name__.lower()

    async def search(
        self,
        query_vector: list[float],  # 稠密向量, 用于语义检索
        project_ids: list[str],
        limit: int = 2,
    ) -> list[ProjectDocumentChunkSearchResponse]:
        """执行稠密向量检索(按项目过滤), 返回按相似度降序排列的分块"""
        from common.config.db import db_vector

        # 谓词预过滤: project_id IN ('id1','id2') (ID 为服务端生成的 UUID, 直接拼接安全)
        where = "project_id IN ({})".format(",".join(f"'{pid}'" for pid in project_ids))
        rows = await db_vector.search_filtered(
            self.collection_name,
            query_vector,
            where=where,
            output_fields=list(ProjectDocumentChunkSearchBase.model_fields.keys()),
            limit=limit,
        )

        # LanceDB 返回 _distance(L2 距离平方, 越小越相关);
        # score 做 1/(1+d) 单调映射(越大越相关), 兼容原检索得分口径
        responses = [
            ProjectDocumentChunkSearchResponse(
                **{k: v for k, v in row.items() if k != "_distance"},
                score=1.0 / (1.0 + row.get("_distance", 0.0)),
            )
            for row in rows
        ]
        return responses

    async def vector_delete_by_document_id(self, document_id: str):
        """按文档ID删除向量库中的全部分块向量

        :param document_id: 文档ID
        """
        from common.config.db import db_vector

        await db_vector.delete_by_filter(
            self.collection_name, f'document_id == "{document_id}"'
        )

    async def vector_delete_by_project_id(self, project_id: str):
        """按项目ID删除向量库中的全部分块向量(清理整个知识库时使用)

        :param project_id: 项目ID
        """
        from common.config.db import db_vector

        await db_vector.delete_by_filter(
            self.collection_name, f'project_id == "{project_id}"'
        )
