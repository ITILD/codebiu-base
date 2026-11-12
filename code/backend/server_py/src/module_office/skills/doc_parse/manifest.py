"""doc_parse Skill Manifest: 文件 → Markdown + 结构块双产物(hybrid, OCR 可降级)

设计落点(04 设计文档 §5.1):
- 包装既有 DocumentParseService(引擎注册表路由 mineru 等), 双产物契约显式化
- nature=hybrid: 解析主干确定; optional=[ocr], OCR 缺失时降级(degraded=true),
  核心文本缺失才失败 —— 降级产物是否可入库由编排层 skip_if 决定(W-2)
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
        key="doc_parse",
        name="文档解析",
        description="将文件解析为 Markdown 与结构块两种产物(markdown 整篇 + blocks 结构小块,"
        "含层级/页码/内容类型)。适合文档入库前解析、对话附件内容提取。",
        category="ingest",
        skill_type="builtin_tool",
        nature=SkillNature.HYBRID.value,
        impl_ref="module_office.skills.doc_parse.impl:run",
        version="1",
        input_schema={
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {"type": "string", "description": "服务端本地文件路径(调用方负责落盘)"},
                "filename": {"type": "string", "description": "原始文件名(决定解析引擎路由, 缺省取路径尾名)"},
                "document_id": {"type": "string", "description": "可选: 知识库文档ID(回写溯源/编排关联用)"},
                "options": {
                    "type": "object",
                    "properties": {"ocr": {"type": "string", "enum": ["auto", "on", "off"]}},
                    "description": "OCR 增强开关(默认 auto: 扫描件自动 OCR)",
                },
                "size_hint": {"type": "integer", "description": "文件字节数(运行时模式决策用)"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "markdown": {"type": "string", "description": "产物一: 整篇 Markdown"},
                "blocks": {"type": "array", "description": "产物二: 结构小块(含层级/页码/内容类型)"},
                "meta": {"type": "object", "description": "parser/ocr_used/degraded/warnings"},
            },
        },
        required_capabilities=[],
        optional_capabilities=["ocr"],  # 缺失时跳过扫描件增强, degraded=true
        capability_alternatives=[],
        execution=ExecutionSpec(
            modes=["inline", "queued"],
            inline_timeout_s=60,
            queued_timeout_s=1800,
            resource_domain="parse",
            inline_max_input_bytes=5 * 1024 * 1024,  # >5MB 文件直接 queued
        ),
        idempotency=IdempotencySpec(keys=["document_id", "file_path"]),
        retry=RetrySpec(max=1, backoff_s=30),
        progress=True,
        cancel=False,
        side_effects="read",
        agent_callable=True,
    )
)
