"""module_rag Skill 资产包(REQ-018, W-13) + 向量存储环境能力探测注册

导入本包即完成 rag 领域 Skill 注册与 store:* 环境特性提供器注册(capability_alternatives
的环境能力分支, 见 module_ai/service/capability_registry.py)。
"""

from module_ai.service.capability_registry import register_feature_provider

from module_rag.skills import doc_chunk_index  # noqa: F401 (导入即注册)


async def _probe_store_feature(suffix: str, user_id: str | None) -> bool:
    """store:* 环境能力探测

    store:bm25 —— 当前唯一向量后端 Milvus 的 content 字段建表即开中文分词全文索引
    (TEXT_MATCH 关键词检索路, 不依赖任何模型) → 恒可用。这是 doc_chunk_index
    零模型降级入库路线的依据(W-6: BM25-only 仅 Milvus)。
    """
    return suffix == "bm25"


register_feature_provider("store", _probe_store_feature)
