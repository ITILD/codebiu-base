"""ocr_image Skill(ai): 下载图片并 OCR 识别(必需 OCR 模型能力)"""

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

# 单图片下载大小上限(15MB, 与 rag 临时文件上限对齐)
_OCR_MAX_BYTES = 15 * 1024 * 1024

register_skill(
    SkillManifest(
        namespace="sys",
        key="ocr_image",
        name="图片文字识别",
        description="下载指定 URL 的图片并识别其中的文字(OCR)。适合读取截图、扫描件中的文字。",
        category="retrieval",
        nature=SkillNature.AI.value,
        impl_ref="module_agent.skills.builtin.ocr_image:run",
        input_schema={
            "type": "object",
            "required": ["image_url"],
            "properties": {
                "image_url": {"type": "string", "description": "图片 URL(http/https)"},
                "lang": {"type": "string", "default": "ch", "description": "识别语言"},
            },
        },
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        required_capabilities=["ocr"],
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=60, resource_domain="llm"),
        idempotency=IdempotencySpec(keys=["image_url"]),
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
    """下载图片并 OCR(用户绑定/全局默认 OCR 模型, 按 ctx.user_id 解析)"""
    import httpx

    image_url = str(skill_input["image_url"])
    await progress(20, "下载图片")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(image_url)
        resp.raise_for_status()
        if len(resp.content) > _OCR_MAX_BYTES:
            return {"text": f"图片过大(超过 {_OCR_MAX_BYTES // 1024 // 1024}MB), 已跳过识别"}
    # cv2 为重依赖, 与 OCR 引擎同惯例延迟导入
    import cv2
    import numpy as np

    image_cv = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)
    if image_cv is None:
        return {"text": "无法解析该图片(格式不支持或已损坏)"}
    await progress(60, "OCR 识别中")
    from module_ai.dependencies.ocr import get_ocr_service

    result = await get_ocr_service().recognize(image_cv, user_id=ctx.user_id)
    texts = [it.get("text", "") for it in (result.get("results") or [])]
    content = "\n".join(t for t in texts if t)
    await progress(100, "识别完成")
    return {"text": content or "未识别到文字"}
