"""prompt 自定义 Skill(REQ-018 批次 2, FEAT-AICAP-009)

- 状态机: draft(草稿) → published(发布, 注册表可见可调用) → deprecated(下线)
- 实现: 无业务代码 —— 运行时内建执行器(模板渲染 {{字段}} + chat 模型调用);
  发布时为每个 prompt Skill 生成专属执行闭包注入 impl 缓存(与 builtin 同一
  load_impl 路径, 三入口一致)
- 版本: 每次模板变更生成新 ai_skill_version 快照(CA-09); 进程重启经
  restore_custom_prompt_skills() 从 DB 恢复注册
"""

import logging
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import select

from common.config.db import db_manager
from common.utils.fastapi_ex.exceptions import BusinessError, ForbiddenError, NotFoundError
from module_agent.do.skill import AiSkill, AiSkillVersion, SkillPublishStatus
from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    RetrySpec,
    SkillManifest,
)
from module_agent.skills.registry import SKILL_REGISTRY, register_skill

logger = logging.getLogger(__name__)

_TEMPLATE_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptFieldDef(BaseModel):
    """prompt Skill 输入字段声明(简单类型, 转 input_schema.properties)"""

    name: str = Field(max_length=50, description="字段名(模板 {{name}} 占位引用)")
    type: str = Field(default="string", description="string/integer/number/boolean")
    required: bool = Field(default=True)
    description: str = Field(default="", max_length=200)


class PromptSkillCreate(BaseModel):
    """创建请求"""

    key: str = Field(max_length=50, description="技能短名(注册键 usr.{key})")
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=2000)
    template: str = Field(min_length=1, description="提示词模板, {{字段}} 占位")
    output_format: str = Field(default="text", description="text/json")
    fields: list[PromptFieldDef] = Field(default_factory=list)
    agent_callable: bool = Field(default=True)


class PromptSkillUpdate(BaseModel):
    """更新请求(全 Optional, 发布后更新生成新版本快照)"""

    name: str | None = None
    description: str | None = None
    template: str | None = None
    output_format: str | None = None
    fields: list[PromptFieldDef] | None = None
    agent_callable: bool | None = None


def _render_template(template: str, values: dict[str, Any]) -> str:
    """渲染 {{字段}} 占位(未知字段保留原样, 便于提示词中写示例花括号)"""

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        value = values.get(name)
        return match.group(0) if value is None else str(value)

    return _TEMPLATE_VAR.sub(_sub, template)


def make_prompt_runner(manifest: SkillManifest):
    """为 prompt Skill 生成专属执行闭包(签名同 impl 契约, 走同一 load_impl 缓存)"""
    template = str((manifest.prompt or {}).get("template") or "")
    output_format = str((manifest.prompt or {}).get("output_format") or "text")

    async def run(
        skill_input: dict,
        ctx,
        caps,
        progress,
    ) -> dict:
        from langchain_core.messages import HumanMessage

        from module_agent.service.skill_runtime import CapabilityMissingError
        from module_rag.service.user_model import UserModelService

        await progress(30, "渲染提示词")
        rendered = _render_template(template, skill_input)
        if output_format == "json":
            rendered += "\n\n请仅输出合法 JSON, 不要包含其它说明文字。"
        await progress(60, "模型生成中")
        llm = await UserModelService().get_llm_by_user_id(ctx.user_id, False)
        if llm is None:
            raise CapabilityMissingError("chat 模型不可用: 请在模型管理中配置对话模型")
        message = await llm.ainvoke([HumanMessage(content=rendered)])
        text = getattr(message, "content", None) or str(message)
        await progress(100, "生成完成")
        # meta.tokens 由观测层经 usage 回填(pipeline 内建批次 3 细化)
        return {"text": text, "meta": {"output_format": output_format}}

    return run


def _build_manifest(
    key: str,
    name: str,
    description: str,
    template: str,
    output_format: str,
    fields: list[PromptFieldDef],
    agent_callable: bool,
    version: str,
) -> SkillManifest:
    """由用户声明构造受契约约束的 SkillManifest(注册期校验即拦截非法声明)"""
    properties: dict[str, Any] = {
        f.name: {"type": f.type, "description": f.description or f.name}
        for f in fields
    } or {"input": {"type": "string", "description": "输入内容(整段传入模板)"}}
    required = [f.name for f in fields if f.required] or list(properties)
    return SkillManifest(
        namespace="usr",
        key=key,
        name=name,
        description=description or f"自定义提示词技能 {name}",
        skill_type="prompt",
        nature="ai",
        impl_ref=f"prompt_skill:usr.{key}",
        version=version,
        input_schema={"type": "object", "required": required, "properties": properties},
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        required_capabilities=["chat"],
        execution=ExecutionSpec(modes=["inline", "queued"], inline_timeout_s=120),
        idempotency=IdempotencySpec(keys=[]),
        retry=RetrySpec(max=0),
        side_effects="none",
        agent_callable=agent_callable,
        prompt={"template": template, "output_format": output_format},
    )


def _register_prompt(manifest: SkillManifest) -> None:
    """发布/恢复: 注册表登记 + impl 缓存注入执行闭包"""
    from module_agent.service import skill_runtime as sr

    register_skill(manifest)
    sr._impl_cache[manifest.impl_ref] = make_prompt_runner(manifest)


def _unregister_prompt(uid: str) -> None:
    from module_agent.service import skill_runtime as sr

    manifest = SKILL_REGISTRY.pop(uid, None)
    if manifest is not None:
        sr._impl_cache.pop(manifest.impl_ref, None)


class PromptSkillService:
    """自定义 prompt Skill 管理(DB 状态机 + 注册表联动)"""

    async def create(self, req: PromptSkillCreate, user_id: str) -> dict:
        uid = f"usr.{req.key}"
        if SKILL_REGISTRY.get(uid) is not None or await self._get_by_key(uid) is not None:
            raise BusinessError(f"技能键已存在: {uid}")
        manifest = _build_manifest(
            req.key, req.name, req.description, req.template, req.output_format,
            req.fields, req.agent_callable, version="1",
        )
        async with db_manager.db_rel.session_factory() as session:
            row = AiSkill(
                key=uid, namespace="usr", name=req.name,
                description=manifest.description, category="generation",
                skill_type="prompt", nature="ai", origin="custom",
                owner_user_id=user_id,
                current_version="1", status=SkillPublishStatus.DRAFT,
            )
            session.add(row)
            await session.flush()
            snapshot = manifest.model_dump(mode="json")
            snapshot["_fields"] = [f.model_dump() for f in req.fields]
            snapshot["_config_hash"] = _config_hash(manifest)
            session.add(
                AiSkillVersion(
                    skill_id=row.id, version="1",
                    config_hash=_config_hash(manifest),
                    manifest_snapshot=snapshot,
                )
            )
            await session.commit()
            await session.refresh(row)
            return {"skill_id": row.id, "key": uid, "status": row.status}

    async def update(self, skill_id: str, req: PromptSkillUpdate, user_id: str) -> dict:
        row, snapshot = await self._load(skill_id)
        self._check_owner(row, user_id)
        if row.status == SkillPublishStatus.DEPRECATED:
            raise BusinessError("已下线技能不可修改(可重新发布为新版本)")
        fields = [
            PromptFieldDef(**f) for f in (snapshot.get("_fields") or [])
        ] if req.fields is None else req.fields
        manifest = _build_manifest(
            key=row.key.split(".", 1)[1],
            name=req.name or row.name,
            description=req.description or snapshot.get("description") or "",
            template=req.template or (snapshot.get("prompt") or {}).get("template", ""),
            output_format=req.output_format or (snapshot.get("prompt") or {}).get("output_format", "text"),
            fields=fields,
            agent_callable=req.agent_callable if req.agent_callable is not None
            else bool(snapshot.get("agent_callable", True)),
            version=row.current_version,
        )
        new_hash = _config_hash(manifest)
        version_changed = new_hash != snapshot.get("_config_hash")
        async with db_manager.db_rel.session_factory() as session:
            db_row = await session.get(AiSkill, skill_id)
            db_row.name = manifest.name
            db_row.description = manifest.description
            if version_changed:
                next_version = _next_version(db_row.current_version)
                db_row.current_version = next_version
                snapshot_data = manifest.model_dump(mode="json")
                snapshot_data["_fields"] = [f.model_dump() for f in fields]
                snapshot_data["_config_hash"] = new_hash
                session.add(
                    AiSkillVersion(
                        skill_id=skill_id, version=next_version,
                        config_hash=new_hash, manifest_snapshot=snapshot_data,
                    )
                )
            await session.commit()
            # 已发布: 重注册生效新版本(版本快照 CA-09: 运行中调用仍用旧快照完成)
            if db_row.status == SkillPublishStatus.PUBLISHED:
                await self._re_register(manifest, version_changed, skill_id)
        return {"skill_id": skill_id, "key": row.key, "version": db_row.current_version}

    async def publish(self, skill_id: str, user_id: str) -> dict:
        row, _ = await self._load(skill_id)
        self._check_owner(row, user_id)
        if row.status == SkillPublishStatus.DEPRECATED:
            raise BusinessError("已下线技能不可发布(请另建新技能)")
        manifest, fields = await self._manifest_from_row(row)
        _register_prompt(manifest)
        async with db_manager.db_rel.session_factory() as session:
            db_row = await session.get(AiSkill, skill_id)
            db_row.status = SkillPublishStatus.PUBLISHED
            db_row.deprecated = False
            await session.commit()
        return {"skill_id": skill_id, "key": row.key, "status": "published"}

    async def deprecate(self, skill_id: str, user_id: str) -> dict:
        """下线: 注册表反注册(新调用被拒) + DB 标记; 历史 skill_invocation 仍可追溯"""
        row, _ = await self._load(skill_id)
        self._check_owner(row, user_id)
        _unregister_prompt(row.key)
        async with db_manager.db_rel.session_factory() as session:
            db_row = await session.get(AiSkill, skill_id)
            db_row.status = SkillPublishStatus.DEPRECATED
            db_row.deprecated = True
            await session.commit()
        return {"skill_id": skill_id, "key": row.key, "status": "deprecated"}

    async def list_custom(self, user_id: str, is_admin: bool = False) -> list[dict]:
        async with db_manager.db_rel.session_factory() as session:
            rows = (
                await session.exec(
                    select(AiSkill).where(AiSkill.origin == "custom")
                )
            ).all()
        return [
            {
                "skill_id": r.id, "key": r.key, "name": r.name,
                "description": r.description, "status": r.status,
                "current_version": r.current_version,
                "agent_callable": bool(SKILL_REGISTRY.get(r.key)),
                "owner_user_id": r.owner_user_id,
            }
            for r in rows
            if is_admin or r.owner_user_id == user_id
        ]

    async def get_detail(self, skill_id: str, user_id: str) -> dict:
        """最新版本快照详情(编辑回显): 模板原文/字段声明/输出格式"""
        row, snapshot = await self._load(skill_id)
        self._check_owner(row, user_id)
        prompt = snapshot.get("prompt") or {}
        return {
            "skill_id": row.id,
            "key": row.key,
            "name": row.name,
            "description": snapshot.get("description") or "",
            "status": row.status,
            "current_version": row.current_version,
            "template": prompt.get("template", ""),
            "output_format": prompt.get("output_format", "text"),
            "fields": snapshot.get("_fields") or [],
            "agent_callable": bool(snapshot.get("agent_callable", True)),
        }

    # ################ 内部 ################

    async def _re_register(self, manifest: SkillManifest, version_changed: bool, skill_id: str) -> None:
        """发布态更新后重注册(version 变更时刷新版本号)"""
        if version_changed:
            async with db_manager.db_rel.session_factory() as session:
                row = await session.get(AiSkill, skill_id)
                manifest = manifest.model_copy(update={"version": row.current_version})
        _unregister_prompt(manifest.uid)
        _register_prompt(manifest)

    async def _load(self, skill_id: str) -> tuple[AiSkill, dict]:
        async with db_manager.db_rel.session_factory() as session:
            row = await session.get(AiSkill, skill_id)
            if row is None:
                raise NotFoundError(f"自定义 Skill 不存在: {skill_id}")
            if row.origin != "custom":
                raise BusinessError("仅自定义 Skill 可管理")
            latest = (
                await session.exec(
                    select(AiSkillVersion).where(AiSkillVersion.skill_id == skill_id)
                    .order_by(AiSkillVersion.created_at.desc()).limit(1)
                )
            ).first()
        return row, dict(latest.manifest_snapshot or {}) if latest else {}

    async def _get_by_key(self, uid: str) -> AiSkill | None:
        async with db_manager.db_rel.session_factory() as session:
            return (
                await session.exec(select(AiSkill).where(AiSkill.key == uid))
            ).first()

    async def _manifest_from_row(self, row: AiSkill) -> tuple[SkillManifest, list[PromptFieldDef]]:
        """从最新版本快照重建 Manifest(重启恢复/发布共用)"""
        async with db_manager.db_rel.session_factory() as session:
            latest = (
                await session.exec(
                    select(AiSkillVersion).where(AiSkillVersion.skill_id == row.id)
                    .order_by(AiSkillVersion.created_at.desc()).limit(1)
                )
            ).first()
        snapshot = dict(latest.manifest_snapshot or {}) if latest else {}
        fields = [PromptFieldDef(**f) for f in (snapshot.get("_fields") or [])]
        prompt = snapshot.get("prompt") or {}
        manifest = _build_manifest(
            key=row.key.split(".", 1)[1],
            name=row.name,
            description=row.description or "",
            template=prompt.get("template", ""),
            output_format=prompt.get("output_format", "text"),
            fields=fields,
            agent_callable=bool(snapshot.get("agent_callable", True)),
            version=row.current_version,
        )
        return manifest, fields

    @staticmethod
    def _check_owner(row: AiSkill, user_id: str) -> None:
        owner = getattr(row, "owner_user_id", None)
        if owner and owner != user_id:
            raise ForbiddenError("仅创建者可管理该自定义 Skill")


def _config_hash(manifest: SkillManifest) -> str:
    import hashlib
    import json

    payload = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _next_version(current: str) -> str:
    """小版本自增: '1' → '2', 'v3' → 'v4'(非数字尾缀时追加 .1)"""
    match = re.match(r"^(.*?)(\d+)$", current)
    if match:
        return f"{match.group(1)}{int(match.group(2)) + 1}"
    return f"{current}.1"


async def restore_custom_prompt_skills() -> dict:
    """启动恢复: 从 DB 读取 published 的自定义 prompt Skill 重新注册(幂等)"""
    restored = 0
    async with db_manager.db_rel.session_factory() as session:
        rows = (
            await session.exec(
                select(AiSkill).where(
                    AiSkill.origin == "custom",
                    AiSkill.skill_type == "prompt",
                    AiSkill.status == SkillPublishStatus.PUBLISHED,
                )
            )
        ).all()
    for row in rows:
        try:
            manifest, _ = await PromptSkillService()._manifest_from_row(row)
            _register_prompt(manifest)
            restored += 1
        except Exception as e:
            logger.warning("自定义 Skill 恢复失败 %s: %s", row.key, e)
    logger.info("自定义 prompt Skill 恢复完成: %s 个", restored)
    return {"restored": restored}
