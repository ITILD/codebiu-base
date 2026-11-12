"""kb_ingest_agent(REQ-018 首个 static_agent 样板, 设计 §3.3/§5.3)

知识库文档入库编排: parse(doc_parse) → index(doc_chunk_index) 两步线性 + documents
fan_out 并发 + collect 容错; 全程可零模型运行(OCR/策略识别/embeddings 均降级)。

编排层降级拦截(W-2): index 步骤 skip_if = "parse.degraded == true" ——
doc_parse 降级产物(OCR 缺失)不得自动入库, 判定在编排层表达, Skill 保持纯粹。
"""

from module_agent.agents.manifest import AgentJobManifest, AgentStepDef, register_agent_job

register_agent_job(
    AgentJobManifest(
        key="kb_ingest_agent",
        name="知识库文档入库",
        description="知识库文档批量解析入库编排: 文档解析(双产物) → 分块向量化入库;"
        "降级产物被编排层拦截不自动入库; 支持整库重建与批量重解析复用。",
        version="1",
        steps=[
            AgentStepDef(
                id="parse",
                skill="sys.doc_parse",
                fan_out="documents",
                item_key="document_id",
                # 展开项输入准备器: 执行侧(inline/worker 同进程)按 document_id 物化
                # 文件(content_hash 定位 → stream 落盘), 临时目录随 job 清理
                input_resolver="module_rag.skills.ingest_support:resolve_document_input",
                on_error="collect",  # 单文档失败不阻塞其他文档
            ),
            AgentStepDef(
                id="index",
                skill="sys.doc_chunk_index",
                depends_on=["parse"],
                fan_out="documents",
                item_key="document_id",
                # 展开项级过滤(W-2): 降级产物不得自动入库 —— 「降级结果是否可用」是
                # 编排决策不是能力语义(同一产物在人工预览场景可用、自动入库场景不可用)
                skip_if="parse.degraded == true",
                consume={
                    "blocks": "parse.blocks",      # 双产物内存传递(不重复解析)
                    "markdown": "parse.markdown",
                },
                on_error="collect",
            ),
        ],
        runtime_policy={
            "priority_class": "batch",
            "max_parallel": 4,
            "budget": {"max_duration_s": 7200},
        },
    )
)
