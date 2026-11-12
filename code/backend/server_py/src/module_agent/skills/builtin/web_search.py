"""web_search Skill(static): 联网搜索引擎查询(不依赖模型)"""

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

register_skill(
    SkillManifest(
        namespace="sys",
        key="web_search",
        name="网络搜索",
        description="联网搜索引擎查询最新信息。适合回答时效性问题、技术资料查找等。",
        category="retrieval",
        nature=SkillNature.STATIC.value,
        impl_ref="module_agent.skills.builtin.web_search:run",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "maxLength": 500, "description": "搜索关键词或问题"},
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10, "description": "返回条数"},
            },
        },
        output_schema={"type": "object", "properties": {"text": {"type": "string"}, "total": {"type": "integer"}}},
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=30, resource_domain="none"),
        idempotency=IdempotencySpec(keys=[]),
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
    """网络搜索(走已配置引擎; 引擎未配置时按 invalid_input 失败并回告)"""
    from module_websearch.service.websearch import WebSearchService
    from module_websearch.utils.websearch.do.websearch import SearchRequest

    await progress(30, "搜索引擎查询中")
    resp = await WebSearchService().search(
        SearchRequest(query=str(skill_input["query"]), limit=int(skill_input.get("limit") or 5))
    )
    lines: list[str] = []
    if not resp.results:
        lines.append("未搜索到相关结果")
    else:
        lines.append(f"网络搜索到 {resp.total} 条结果:")
        for idx, item in enumerate(resp.results, start=1):
            desc = (item.description or "").replace("\n", " ")[:200]
            lines.append(f"{idx}. [{item.source or item.engine.value}] {item.title}")
            lines.append(f"   摘要: {desc}")
            lines.append(f"   链接: {item.url}")
    await progress(100, "搜索完成")
    return {"text": "\n".join(lines), "total": resp.total}
