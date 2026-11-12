"""Skill 资产同步(REQ-018, W-8 双生命周期: 代码为源的只读同步)

内置 Skill 以代码注册表为准: 启动时同步 ai_skill/ai_skill_version ——
新增即发布、删除即下线(deprecated)、声明变化(config_hash)即新版本快照;
运行期固定版本快照(CA-09)依据 ai_skill_version.manifest_snapshot。
"""

import hashlib
import logging

from sqlmodel import select

from common.config.db import db_manager
from module_agent.do.skill import (
    AiSkill,
    AiSkillVersion,
    SkillPublishStatus,
)

logger = logging.getLogger(__name__)


def _config_hash(manifest) -> str:
    return hashlib.sha256(manifest.model_dump_json().encode()).hexdigest()


async def sync_builtin_skills() -> dict:
    """启动同步(幂等): SKILL_REGISTRY → ai_skill + ai_skill_version; 移除项置 deprecated"""
    from module_agent.skills.registry import list_manifests

    stats = {"published": 0, "updated": 0, "deprecated": 0}
    registered_keys: set[str] = set()
    async with db_manager.db_rel.session_factory() as session:
        for manifest in list_manifests():
            registered_keys.add(manifest.uid)
            config_hash = _config_hash(manifest)
            row = (
                await session.exec(select(AiSkill).where(AiSkill.key == manifest.uid))
            ).first()
            snapshot = manifest.model_dump(mode="json")
            if row is None:
                row = AiSkill(
                    key=manifest.uid,
                    namespace=manifest.namespace,
                    name=manifest.name,
                    description=manifest.description,
                    category=manifest.category,
                    skill_type=manifest.skill_type,
                    nature=manifest.nature,
                    origin="builtin",
                    current_version=manifest.version,
                    status=SkillPublishStatus.PUBLISHED,
                    deprecated=False,
                )
                session.add(row)
                await session.flush()  # 取 row.id
                session.add(
                    AiSkillVersion(
                        skill_id=row.id, version=manifest.version,
                        config_hash=config_hash, manifest_snapshot=snapshot,
                    )
                )
                stats["published"] += 1
                continue
            # 已登记: 版本或声明漂移 → 更新 + 新版本快照
            latest = (
                await session.exec(
                    select(AiSkillVersion)
                    .where(AiSkillVersion.skill_id == row.id)
                    .order_by(AiSkillVersion.created_at.desc())
                    .limit(1)
                )
            ).first()
            drifted = latest is None or latest.config_hash != config_hash
            if (
                row.current_version != manifest.version
                or row.name != manifest.name
                or row.description != manifest.description
                or drifted
            ):
                row.current_version = manifest.version
                row.name = manifest.name
                row.description = manifest.description
                row.category = manifest.category
                row.skill_type = manifest.skill_type
                row.nature = manifest.nature
                row.deprecated = False
                if drifted:
                    session.add(
                        AiSkillVersion(
                            skill_id=row.id, version=manifest.version,
                            config_hash=config_hash, manifest_snapshot=snapshot,
                        )
                    )
                stats["updated"] += 1
        # 代码中已删除的内置 Skill → 下线(保留历史观测可追溯)
        rows = (
            await session.exec(select(AiSkill).where(AiSkill.origin == "builtin"))
        ).all()
        for row in rows:
            if row.key not in registered_keys and not row.deprecated:
                row.deprecated = True
                row.status = SkillPublishStatus.DEPRECATED
                stats["deprecated"] += 1
        await session.commit()
    logger.info("Skill 资产同步完成: %s", stats)
    return stats
