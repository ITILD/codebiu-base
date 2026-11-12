"""SkillRuntime 统一调用测试(REQ-018 批次 1): 三入口汇合的执行/观测/降级"""

import pytest

from module_agent.service import skill_runtime as sr
from module_agent.service.skill_runtime import SkillContext, SkillRuntime
from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    SkillManifest,
    SkillNature,
)
from module_agent.skills.registry import SKILL_REGISTRY, register_skill


def _register(key: str, *, nature: str = "static", execution: ExecutionSpec | None = None, **kw):
    """注册测试技能(impl 经缓存注入 fake, 免真实实现模块)"""
    impl_ref = f"tst.fake_impls:{key}"
    manifest = SkillManifest(
        namespace="tst",
        key=key,
        name=f"测试-{key}",
        description="单测临时技能",
        nature=nature,
        impl_ref=impl_ref,
        input_schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"y": {"type": "string"}}},
        execution=execution or ExecutionSpec(modes=["inline"], inline_timeout_s=5),
        idempotency=IdempotencySpec(keys=["x"]),
        **kw,
    )
    register_skill(manifest)
    return manifest


@pytest.fixture
def echo_skill():
    """echo 技能: 返回 {y: input.x}"""
    manifest = _register("echo")

    async def _run(skill_input, ctx, caps, progress):
        await progress(50, "中途")
        return {"y": str(skill_input["x"])}

    sr._impl_cache[manifest.impl_ref] = _run
    yield manifest
    SKILL_REGISTRY.pop(manifest.uid, None)
    sr._impl_cache.pop(manifest.impl_ref, None)


@pytest.fixture
def zero_model_env(monkeypatch):
    """零模型环境(CA-06): 所有能力解析均不可满足"""
    from module_ai.service import capability_registry

    async def _unavailable(key, user_id=None):
        return capability_registry.ResolvedCapability(
            capability_key=key, kind="none", available=False
        )

    monkeypatch.setattr(capability_registry, "resolve", _unavailable)


def _ctx(**kw) -> SkillContext:
    return SkillContext(user_id="pytest-user", entry="debug", **kw)


class TestInvokeInline:
    async def test_success_envelope_and_observation(self, echo_skill):
        runtime = SkillRuntime()
        envelope = await runtime.invoke("tst.echo", {"x": "hello"}, _ctx())
        assert envelope["status"] == "succeeded"
        assert envelope["result"] == {"y": "hello"}
        assert envelope["invocation_id"]
        assert envelope["error"] is None
        # 观测落库(CA-11)
        row = await runtime.get_invocation(envelope["invocation_id"])
        assert row is not None and row.status == "succeeded"
        assert row.user_id == "pytest-user" and row.entry == "debug"

    async def test_failure_with_error_class(self):
        manifest = _register("boom")

        async def _run(skill_input, ctx, caps, progress):
            raise ValueError("参数不对")

        sr._impl_cache[manifest.impl_ref] = _run
        try:
            envelope = await SkillRuntime().invoke("tst.boom", {"x": "1"}, _ctx())
            assert envelope["status"] == "failed"
            assert envelope["error"]["class"] == "invalid_input"
            assert "参数不对" in envelope["error"]["message"]
        finally:
            SKILL_REGISTRY.pop(manifest.uid, None)
            sr._impl_cache.pop(manifest.impl_ref, None)

    async def test_unknown_skill(self):
        envelope = await SkillRuntime().invoke("tst.not_exist", {"x": "1"}, _ctx())
        assert envelope["status"] == "failed"
        assert envelope["error"]["class"] == "invalid_input"


class TestCapabilityPaths:
    """能力解析三分支: 快速失败 / 降级 / 能力组"""

    async def test_required_missing_fast_fail(self, zero_model_env):
        manifest = _register("needs_model", nature="ai", required_capabilities=["chat"])

        async def _run(skill_input, ctx, caps, progress):  # pragma: no cover 不应执行
            return {}

        sr._impl_cache[manifest.impl_ref] = _run
        try:
            envelope = await SkillRuntime().invoke("tst.needs_model", {"x": "1"}, _ctx())
            assert envelope["status"] == "failed"
            assert envelope["error"]["class"] == "capability_missing"
            row = await SkillRuntime().get_invocation(envelope["invocation_id"])
            assert row.error_class == "capability_missing"
        finally:
            SKILL_REGISTRY.pop(manifest.uid, None)
            sr._impl_cache.pop(manifest.impl_ref, None)

    async def test_optional_missing_degrades(self, echo_skill, monkeypatch):
        """hybrid 可选能力缺失 → 降级执行成功且 degraded=true(零模型环境可跑, CA-06)"""
        from module_ai.service import capability_registry

        async def _resolve(key, user_id=None):
            return capability_registry.ResolvedCapability(
                capability_key=key, kind="none", available=False
            )

        monkeypatch.setattr(capability_registry, "resolve", _resolve)
        # echo 改造为 hybrid(重注册同名不同声明会冲突 → 用新技能)
        manifest = _register(
            "hybrid_echo", nature="hybrid", optional_capabilities=["ocr"]
        )

        async def _run(skill_input, ctx, caps, progress):
            assert caps.degraded and "ocr" in caps.missing_optional
            return {"y": str(skill_input["x"])}

        sr._impl_cache[manifest.impl_ref] = _run
        try:
            envelope = await SkillRuntime().invoke("tst.hybrid_echo", {"x": "ok"}, _ctx())
            assert envelope["status"] == "succeeded"
            assert envelope["degraded"] is True
        finally:
            SKILL_REGISTRY.pop(manifest.uid, None)
            sr._impl_cache.pop(manifest.impl_ref, None)

    async def test_alternatives_fallback_group(self, monkeypatch):
        """能力组降级(W-6): 首选组不可用落入 store:bm25 组 → degraded"""
        from module_ai.service import capability_registry

        async def _resolve(key, user_id=None):
            available = key.startswith("store:")
            return capability_registry.ResolvedCapability(
                capability_key=key,
                kind="feature" if available else "none",
                available=available,
            )

        monkeypatch.setattr(capability_registry, "resolve", _resolve)
        manifest = _register(
            "alt_skill",
            nature="hybrid",
            capability_alternatives=[["embeddings"], ["store:bm25"]],
        )

        async def _run(skill_input, ctx, caps, progress):
            assert caps.group_satisfies("store:bm25") and not caps.group_satisfies("embeddings")
            return {"y": "keyword_route"}

        sr._impl_cache[manifest.impl_ref] = _run
        try:
            envelope = await SkillRuntime().invoke("tst.alt_skill", {"x": "1"}, _ctx())
            assert envelope["status"] == "succeeded" and envelope["degraded"] is True
        finally:
            SKILL_REGISTRY.pop(manifest.uid, None)
            sr._impl_cache.pop(manifest.impl_ref, None)


class TestModeDecisionAndIdempotency:
    def test_decide_mode_rules(self, echo_skill):
        manifest = echo_skill
        # 声明只支持 inline: 即使 batch 也不转 queued(声明优先, §4.2)
        assert SkillRuntime.decide_mode(
            manifest, {}, _ctx(priority_class="batch"), "auto"
        ) == "inline"
        # 声明双形态 + 输入规模超阈值 → queued
        big = ExecutionSpec(modes=["inline", "queued"], inline_max_input_bytes=100)
        holder = type("M", (), {"execution": big, "uid": "t"})()
        assert SkillRuntime.decide_mode(holder, {"size_hint": 1000}, _ctx(), "auto") == "queued"
        assert SkillRuntime.decide_mode(holder, {"size_hint": 10}, _ctx(), "auto") == "inline"
        # 声明双形态 + batch → queued
        assert SkillRuntime.decide_mode(holder, {}, _ctx(priority_class="batch"), "auto") == "queued"
        # 不支持的显式 mode 拒绝
        with pytest.raises(ValueError, match="不支持"):
            SkillRuntime.decide_mode(manifest, {}, _ctx(), "queued")

    async def test_idempotency_reuse_running_and_rerun_succeeded(self, echo_skill):
        """进行中复用(防重复提交); 已成功不复用(重跑语义, 设计 §5.1)"""
        runtime = SkillRuntime()
        first = await runtime.invoke("tst.echo", {"x": "same"}, _ctx())
        assert first["status"] == "succeeded"
        second = await runtime.invoke("tst.echo", {"x": "same"}, _ctx())
        assert second["invocation_id"] != first["invocation_id"]  # 成功后可重跑

        # 手工制造 running 行 → 同指纹复用
        from module_agent.do.skill import InvocationStatus, SkillInvocation
        from common.config.db import db_manager

        manifest = echo_skill
        fingerprint = runtime._idempotency_fingerprint(manifest, {"x": "concurrent"})
        assert fingerprint is not None
        async with db_manager.db_rel.session_factory() as session:
            running = SkillInvocation(
                skill_key=manifest.uid, skill_version="1", mode="inline",
                status=InvocationStatus.RUNNING, idempotency_key=fingerprint,
                input_summary={}, user_id="pytest-user",
            )
            session.add(running)
            await session.commit()
            await session.refresh(running)
            running_id = running.invocation_id
        try:
            third = await runtime.invoke("tst.echo", {"x": "concurrent"}, _ctx())
            assert third["invocation_id"] == running_id
        finally:
            async with db_manager.db_rel.session_factory() as session:
                row = await session.get(SkillInvocation, running_id)
                if row is not None:
                    await session.delete(row)
                    await session.commit()


class TestToolResultRendering:
    """W-10: 对话工具失败文案按 error_class 固定映射"""

    def test_success_text_passthrough(self):
        from module_agent.skills.adapter import _render_tool_result

        out = _render_tool_result(
            {"status": "succeeded", "result": {"text": "答案内容"}, "degraded": False}
        )
        assert out == "答案内容"

    def test_capability_missing_message(self):
        from module_agent.skills.adapter import _render_tool_result

        out = _render_tool_result(
            {"status": "failed", "error": {"class": "capability_missing", "message": "x"}}
        )
        assert "capability_missing" in out and "模型" in out

    def test_permanent_failure_message(self):
        from module_agent.skills.adapter import _render_tool_result

        out = _render_tool_result(
            {"status": "failed", "error": {"class": "permanent", "message": "崩溃"}}
        )
        assert "执行失败" in out
