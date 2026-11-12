"""doc_chunk_index Skill Manifest: 分块策略 + 向量化 + 入库(hybrid, W-6 能力组)

设计落点(04 设计文档 §5.2):
- 实现 = 分块策略(规则 + 可选 chat 识别) + 向量化 + 入库(Milvus) + 引用记录
- capability_alternatives = [[embeddings], [store:bm25]]:
    首选组(完整路线): embeddings 必需 → 全量向量入库
    降级组: store:bm25(Milvus 全文索引, 零模型可跑) → 零向量入库 + degraded=true,
            检索走关键词路; 配置 embeddings 后经全库重向量化恢复语义检索
- nature=hybrid: 策略识别(chat)缺失降级为默认策略 general
"""

from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    RetrySpec,
    SkillManifest,
    SkillNature,
)
from module_agent.skills.registry import register_skill

register_skill(
    SkillManifest(
        namespace="sys",
        key="doc_chunk_index",
        name="文档分块入库",
        description="将文档解析产物(结构块)按策略重新分块并写入知识库向量表:"
        "策略识别(可选 AI)→ 重分块 → 向量化(Milvus) → 入库并更新文档状态。",
        category="ingest",
        skill_type="builtin_tool",
        nature=SkillNature.HYBRID.value,
        impl_ref="module_rag.skills.doc_chunk_index.impl:run",
        version="1",
        input_schema={
            "type": "object",
            "required": ["document_id", "blocks"],
            "properties": {
                "document_id": {"type": "string", "description": "知识库文档ID(入库归属)"},
                "blocks": {
                    "type": "array",
                    "description": "doc_parse 产出的结构块列表(编排层传递, 不重复解析)",
                },
                "markdown": {"type": "string", "description": "可选: 整篇 Markdown(策略识别取样用)"},
                "chunk_config": {"type": "object", "description": "可选: 分块参数覆盖"},
                "size_hint": {"type": "integer", "description": "源文件字节数(模式决策用)"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "chunk_count": {"type": "integer", "description": "入库分块数"},
                "strategy": {"type": "string", "description": "实际生效分块策略"},
                "route": {"type": "string", "enum": ["vector", "keyword_only"], "description": "入库路线"},
                "meta": {"type": "object"},
            },
        },
        required_capabilities=[],
        optional_capabilities=["chat"],  # 策略识别模型, 缺失降级默认策略 general
        capability_alternatives=[["embeddings"], ["store:bm25"]],
        execution=ExecutionSpec(
            modes=["inline", "queued"],
            inline_timeout_s=120,
            queued_timeout_s=1800,
            resource_domain="index",
            inline_max_input_bytes=2 * 1024 * 1024,  # >2MB 文档直接 queued
        ),
        idempotency=IdempotencySpec(keys=["document_id"]),
        retry=RetrySpec(max=1, backoff_s=30),
        progress=True,
        cancel=True,
        side_effects="write",
        agent_callable=True,
    )
)
