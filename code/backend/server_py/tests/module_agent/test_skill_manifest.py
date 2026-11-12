"""Skill Manifest 契约与注册表测试(REQ-018 批次 1)"""

import pytest

from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    SkillManifest,
    tool_name_to_uid,
)
from module_agent.skills.registry import (
    SKILL_REGISTRY,
    get_skill,
    list_manifests,
    list_skill_infos,
    register_skill,
)


def _base_manifest(**overrides) -> SkillManifest:
    """最小合法 Manifest(static)"""
    params = dict(
        namespace="tst",
        key="unit_skill",
        name="单测技能",
        description="测试用",
        impl_ref="tests.fake:run",
        input_schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"y": {"type": "string"}}},
    )
    params.update(overrides)
    return SkillManifest(**params)


class TestManifestInvariants:
    """契约校验规则(设计 §3.1)"""

    def test_valid_static_manifest(self):
        m = _base_manifest()
        assert m.uid == "tst.unit_skill"
        assert m.tool_name == "tst_unit_skill"
        assert tool_name_to_uid(m.tool_name) == m.uid

    def test_static_must_not_declare_capabilities(self):
        with pytest.raises(ValueError, match="static"):
            _base_manifest(required_capabilities=["chat"])

    def test_ai_requires_capabilities(self):
        with pytest.raises(ValueError, match="nature=ai"):
            _base_manifest(nature="ai")

    def test_hybrid_requires_degradation_path(self):
        with pytest.raises(ValueError, match="hybrid"):
            _base_manifest(nature="hybrid")

    def test_hybrid_with_optional_ok(self):
        m = _base_manifest(nature="hybrid", optional_capabilities=["ocr"])
        assert m.nature == "hybrid"

    def test_input_schema_required_mandatory(self):
        with pytest.raises(ValueError, match="required"):
            _base_manifest(input_schema={"type": "object", "properties": {"x": {"type": "string"}}})

    def test_queued_requires_progress(self):
        with pytest.raises(ValueError, match="queued"):
            _base_manifest(execution=ExecutionSpec(modes=["queued"]), progress=False)

    def test_illegal_key_rejected(self):
        with pytest.raises(ValueError, match="key 非法"):
            _base_manifest(key="Bad-Key")


class TestRegistry:
    """注册表行为: 幂等注册/冲突检测/短名兼容解析"""

    def test_register_idempotent_and_conflict(self):
        m1 = _base_manifest(key="reg_skill")
        register_skill(m1)
        register_skill(m1)  # 同声明幂等
        m2 = _base_manifest(key="reg_skill", description="变更后")  # 冲突抛错
        with pytest.raises(ValueError, match="冲突"):
            register_skill(m2)
        SKILL_REGISTRY.pop("tst.reg_skill")

    def test_short_name_compat_resolution(self):
        """旧短名(无命名空间)自动映射 —— 存量 agent.skills 无感迁移(W-9)"""
        m = _base_manifest(key="legacy_skill")
        register_skill(m)
        try:
            assert get_skill("tst.legacy_skill") is m
            assert get_skill("legacy_skill") is m  # 短名兼容
            assert get_skill("no_such_skill") is None
        finally:
            SKILL_REGISTRY.pop("tst.legacy_skill")

    def test_builtin_skills_registered(self):
        """装配收集后: 双 Skill 样板 + 4 迁移技能在注册表"""
        import module_agent.skills  # noqa: F401 (触发收集)

        keys = {m.uid for m in list_manifests()}
        assert "sys.doc_parse" in keys
        assert "sys.doc_chunk_index" in keys
        assert {"sys.web_search", "sys.ocr_image", "sys.file_search", "sys.rag_qa"} <= keys
        infos = list_skill_infos()
        assert any(i["key"] == "sys.doc_parse" and i["nature"] == "hybrid" for i in infos)
        # doc_chunk_index 声明能力组(W-6)
        parse = next(i for i in infos if i["key"] == "sys.doc_chunk_index")
        assert parse["capabilities"]["alternatives"] == [["embeddings"], ["store:bm25"]]
