"""Skill Manifest 注册表(REQ-018): 进程内唯一的能力资产登记处

- 各领域宿主模块(module_office/module_rag/...)的 skills/ 包在导入时声明并注册
  (Skill 是宿主模块的对外资产, W-13); module_agent/skills/__init__.py 统一收集
- key 唯一性 = {namespace}.{key}(W-7); 注册即校验契约(CA-03 等), 违反直接抛错
- 兼容解析: 旧短名(web_search)自动映射 sys 命名空间短名, 存量 agent.skills 无感迁移
"""

import logging

from module_agent.skills.manifest import SkillManifest

logger = logging.getLogger(__name__)

# 全局注册表(uid -> SkillManifest)
SKILL_REGISTRY: dict[str, SkillManifest] = {}


def register_skill(manifest: SkillManifest) -> SkillManifest:
    """注册 Skill(重复注册同版本幂等跳过, 冲突即抛错保证启动期暴露)"""
    uid = manifest.uid
    existed = SKILL_REGISTRY.get(uid)
    if existed is not None:
        if existed == manifest:
            return existed  # 幂等(多路径导入)
        raise ValueError(
            f"Skill 注册冲突: {uid} 已存在且声明不一致(旧 v{existed.version} / 新 v{manifest.version})"
        )
    SKILL_REGISTRY[uid] = manifest
    logger.debug("Skill 已注册: %s", uid)
    return manifest


def get_skill(skill_key: str) -> SkillManifest | None:
    """按键查找 Skill

    :param skill_key: 完整键(sys.web_search)或旧短名(web_search, 自动映射 sys 命名空间)
    """
    direct = SKILL_REGISTRY.get(skill_key)
    if direct is not None:
        return direct
    if "." not in skill_key:  # 旧短名兼容: 存量 agent.skills 无感迁移到 {ns}.{key}
        candidates = [m for m in SKILL_REGISTRY.values() if m.key == skill_key]
        if len(candidates) == 1:
            return candidates[0]
    return None


def require_skill(skill_key: str) -> SkillManifest:
    """按键查找, 不存在即抛错(invoker/编排层用)"""
    manifest = get_skill(skill_key)
    if manifest is None:
        from common.utils.fastapi_ex.exceptions import NotFoundError

        raise NotFoundError(f"未注册的 Skill: {skill_key}")
    return manifest


def list_manifests(agent_callable_only: bool = False) -> list[SkillManifest]:
    """Skill 清单(注册顺序; agent_callable_only=True 时仅暴露给对话 tool-calling 的项)"""
    items = list(SKILL_REGISTRY.values())
    if agent_callable_only:
        items = [m for m in items if m.agent_callable]
    return items


def list_skill_infos() -> list[dict]:
    """技能清单视图(Manifest 全量字段, /agent/skills 契约一步到位, W-9)"""
    return [_manifest_view(m) for m in SKILL_REGISTRY.values()]


def _manifest_view(m: SkillManifest) -> dict:
    """Manifest 对外视图(前端能力中心/助手编辑器共用)"""
    return {
        "key": m.uid,
        "name": m.name,
        "description": m.description,
        "category": m.category,
        "skill_type": m.skill_type,
        "nature": m.nature,
        "version": m.version,
        "side_effects": m.side_effects,
        "agent_callable": m.agent_callable,
        "capabilities": {
            "required": m.required_capabilities,
            "optional": m.optional_capabilities,
            "alternatives": m.capability_alternatives,
        },
        "execution": m.execution.model_dump(),
        "input_schema": m.input_schema,
        "output_schema": m.output_schema,
    }
