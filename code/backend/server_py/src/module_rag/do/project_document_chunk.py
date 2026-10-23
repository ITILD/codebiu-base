"""知识库模块 project_document_chunk 表模型与请求/响应体定义"""

from pydantic import BaseModel, Field
# VectorModel
from common.utils.db.orm.vector_model import VectorModel
from module_office.utils.file_parse.do.chunk import Chunk, ContentType, Position
from uuid import uuid4

# 拆分到向量库的内容
class ProjectDocumentChunkBase(VectorModel):
    id: str = Field(primary_key=True,default_factory=lambda: uuid4().hex, description="分块唯一ID")
    sort: int = Field(default=0, description="排序,默认0")
    document_id: str = Field(description="所属文档ID")
    project_id: str = Field(description="所属项目ID")
    content: str = Field(
        description="文本内容",
        # Milvus 全文检索: 中文分词器 + TEXT_MATCH 谓词(关键词召回路走全文索引而非标量 like)
        json_schema_extra={
            "max_length": 8192,
            "milvus_enable_analyzer": True,
            "milvus_analyzer_params": {"type": "chinese"},
            "milvus_enable_match": True,
        },
    )
    source: str = Field(default="", description="来源")
    content_types: list[str] = Field([ContentType.TEXT], description="包含的内容类型")
    position: Position = Field(
        Position(),
        description="位置",
        # Milvus 建表用: 嵌套模型显式声明 JSON 存储(默认回退 VARCHAR 无法承载 dict)
        json_schema_extra={"milvus_dtype": "JSON"},
    )
    # 非标
    # LanceModel 不支持 dict 注解, 聚合元数据以 JSON 字符串存储
    metadata: str | None = Field(
        None,
        description="聚合的非标元数据(JSON 字符串)",
    )
# 拆分到向量库的内容
class ProjectDocumentChunk(ProjectDocumentChunkBase, table=True):
    embedding: list[float] = Field(
        description="向量数据",
        json_schema_extra={"vector_dim": 1024},
    )

# ###########################查询使用

class SearchRequest(BaseModel):
    project_ids: list[str] = Field(description="项目ID列表")
    limit: int = Field(default=2, description="返回的最大结果数,默认2")
    query_content: str = Field(default="", description="用于向量/语义搜索的查询内容")
    keyword_query: str = Field(
        default="", description="关键词检索语句(空格分词, 最多取3个关键词做包含匹配); 为空仅走向量一路"
    )
    score_threshold: float = Field(default=0.5, description="Rerank分数阈值(归一化后0~1),低于此值的结果将被过滤")
    enable_rerank: bool = Field(default=False, description="是否启用Rerank精排(深度思考)")
    rerank_limit: int = Field(default=10, description="Rerank精排返回的最大结果数,默认20")


class ProjectDocumentChunkSearchBase(ProjectDocumentChunkBase):
   pass
 

class ProjectDocumentChunkSearchResponse(ProjectDocumentChunkSearchBase):
    score: float = Field(default=1.0, description="RRF融合得分,越大越相关")





if __name__ == "__main__":
    from common.config.db import db_vector
    import asyncio

    async def main():
        await db_vector.create_table(ProjectDocumentChunk, {"embedding": 1024})

    asyncio.run(main())
