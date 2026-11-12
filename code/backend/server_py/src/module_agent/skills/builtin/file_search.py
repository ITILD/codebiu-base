"""file_search Skill(static): 文件系统全树模糊检索(不依赖模型)"""

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
        key="file_search",
        name="文件检索",
        description="按关键词模糊搜索文件系统中的文件与目录(名称/路径匹配)。适合帮用户定位文件位置。",
        category="retrieval",
        nature=SkillNature.STATIC.value,
        impl_ref="module_agent.skills.builtin.file_search:run",
        input_schema={
            "type": "object",
            "required": ["keyword"],
            "properties": {
                "keyword": {"type": "string", "maxLength": 200, "description": "文件名或路径关键词"},
                "size": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50, "description": "返回条数"},
            },
        },
        output_schema={"type": "object", "properties": {"text": {"type": "string"}, "total": {"type": "integer"}}},
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=30, resource_domain="none"),
        idempotency=IdempotencySpec(keys=["keyword"]),
        retry=RetrySpec(max=0),
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
    """全树模糊搜索文件/目录(名称或逻辑路径匹配, 走 FileService)"""
    from common.utils.db.schema.pagination import PaginationParams
    from module_file.service.filesystem import FileService

    await progress(40, "检索文件系统中")
    page = await FileService().search(
        str(skill_input["keyword"]), PaginationParams(page=1, size=int(skill_input.get("size") or 20))
    )
    lines: list[str] = []
    if not page.items:
        lines.append("未找到相关文件")
    else:
        lines.append(f"检索到 {page.total} 条文件/目录(展示前 {len(page.items)} 条):")
        for idx, entry in enumerate(page.items, start=1):
            kind = "目录" if getattr(entry, "is_dir", False) else "文件"
            lines.append(
                f"{idx}. [{kind}] {getattr(entry, 'name', '')} ({getattr(entry, 'logical_path', '')})"
            )
    await progress(100, "检索完成")
    return {"text": "\n".join(lines), "total": page.total}
