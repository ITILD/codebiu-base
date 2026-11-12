"""kb_ingest_agent 编排测试(REQ-018 批次 1 验收)

- W-2: doc_parse 降级产物被编排层 skip_if 拦截、不自动入库
- W-3: agent_job_run 可查(步骤状态含 when/skip_if 判定结果)
- 上游失败项不向下游传播; collect 容错语义
"""

import pytest

from module_agent.agents import AGENT_JOBS, get_agent_job
from module_agent.agents.manifest import AgentJobManifest, AgentStepDef, register_agent_job
from module_agent.service import skill_runtime as sr
from module_agent.service.agent_job import AgentJobService
from module_agent.service.skill_runtime import SkillContext
from module_agent.skills.manifest import ExecutionSpec, SkillManifest
from module_agent.skills.registry import SKILL_REGISTRY, register_skill


def _register_skill(key: str, fn) -> SkillManifest:
    manifest = SkillManifest(
        namespace="tst",
        key=key,
        name=f"测试-{key}",
        description="编排单测临时技能",
        impl_ref=f"tst.job_impls:{key}",
        input_schema={"type": "object", "required": ["document_id"], "properties": {"document_id": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=5),
    )
    register_skill(manifest)
    sr._impl_cache[manifest.impl_ref] = fn
    return manifest


class _Cleaner:
    """测试资产回收(技能/job agent/impl 缓存)"""

    def __init__(self):
        self.skills: list[str] = []
        self.jobs: list[str] = []

    def skill(self, m: SkillManifest):
        self.skills.append(m.uid)
        return m

    def job(self, m: AgentJobManifest):
        self.jobs.append(m.agent_key)
        return m

    def cleanup(self):
        for uid in self.skills:
            SKILL_REGISTRY.pop(uid, None)
        for key in self.jobs:
            AGENT_JOBS.pop(key, None)
        sr._impl_cache.pop("tst.job_impls", None)


@pytest.fixture
def cleaner():
    c = _Cleaner()
    yield c
    c.cleanup()


def _job(steps, key="ingest_test") -> AgentJobManifest:
    return AgentJobManifest(
        key=key,
        name=f"测试编排-{key}",
        description="单测",
        steps=steps,
    )


class TestKbIngestRegistration:
    def test_kb_ingest_agent_registered(self):
        """内置 kb_ingest_agent 声明完整(步骤/条件/策略), check_invariants 通过"""
        manifest = get_agent_job("sys.kb_ingest_agent")
        assert manifest is not None
        assert [s.id for s in manifest.steps] == ["parse", "index"]
        parse_step, index_step = manifest.steps
        assert parse_step.skill == "sys.doc_parse"
        assert index_step.skip_if == "parse.degraded == true"
        assert index_step.consume == {"blocks": "parse.blocks", "markdown": "parse.markdown"}
        assert manifest.decision_mode == "rule"


class TestOrchestration:
    async def test_degraded_parse_skipped_from_index(self, cleaner):
        """W-2 验收: 解析降级(degraded=true)的文档被 index 步骤 skip_if 拦截"""
        recorded_index_inputs: list[dict] = []

        # envelope.degraded 来自能力解析而非 impl; 为验证 skip_if 链路,
        # 用 monkeypatch 把 parse 的调用信封 degraded 置 True(模拟 OCR 缺失环境)
        async def _parse_impl(skill_input, ctx, caps, progress):
            return {"markdown": "md", "blocks": [{"content": "b"}], "meta": {}}

        async def _index_impl(skill_input, ctx, caps, progress):
            recorded_index_inputs.append(dict(skill_input))
            return {"chunk_count": 1}

        cleaner.skill(_register_skill("j_parse", _parse_impl))
        cleaner.skill(_register_skill("j_index", _index_impl))
        cleaner.job(
            register_agent_job(
                _job([
                    AgentStepDef(id="parse", skill="tst.j_parse", fan_out="documents"),
                    AgentStepDef(
                        id="index", skill="tst.j_index", depends_on=["parse"],
                        fan_out="documents", skip_if="parse.degraded == true",
                        consume={"blocks": "parse.blocks"},
                    ),
                ])
            )
        )

        # 拦截 runtime.invoke: 对 j_parse 的调用返回 degraded 信封(模拟 OCR 缺失)
        real_runtime_invoke = sr.SkillRuntime.invoke

        async def _patched_invoke(self, skill_key, skill_input, ctx, mode="auto", timeout_s=None):
            envelope = await real_runtime_invoke(self, skill_key, skill_input, ctx, mode, timeout_s)
            if skill_key == "tst.j_parse" and str(skill_input.get("document_id", "")).endswith("_bad"):
                envelope = {**envelope, "degraded": True}
            return envelope

        sr.SkillRuntime.invoke = _patched_invoke
        try:
            outcome = await AgentJobService().submit(
                "sys.ingest_test",
                {"documents": [
                    {"document_id": "doc_ok"},
                    {"document_id": "doc_bad"},
                ]},
                SkillContext(user_id="pytest-user", entry="debug"),
                mode="inline",
            )
        finally:
            sr.SkillRuntime.invoke = real_runtime_invoke

        assert outcome["status"] == "succeeded"
        # index 只收到未降级文档(W-2: 降级产物不自动入库)
        assert [i["document_id"] for i in recorded_index_inputs] == ["doc_ok"]
        assert recorded_index_inputs[0]["blocks"] == [{"content": "b"}]  # consume 传递

        # W-3: steps_state 可查, skip_if 判定结果落库
        run = await AgentJobService().get(outcome["job_run_id"])
        assert run is not None
        items = run.steps_state["index"]["items"]
        assert items["doc_bad"]["status"] == "skipped"
        assert items["doc_bad"]["skip_if"] == {"expr": "parse.degraded == true", "result": True}
        assert items["doc_ok"]["status"] == "succeeded"
        assert run.progress["total"] == 4 and run.progress["processed"] == 4

    async def test_upstream_failure_not_propagated(self, cleaner):
        """上游失败项不进入下游(dependency_failed 拦截); collect 下 job 不中止"""
        recorded_index: list[str] = []

        async def _parse(skill_input, ctx, caps, progress):
            if str(skill_input["document_id"]).endswith("_broken"):
                raise ValueError("解析失败")
            return {"blocks": [{"content": "ok"}], "meta": {}}

        async def _index(skill_input, ctx, caps, progress):
            recorded_index.append(str(skill_input["document_id"]))
            return {"chunk_count": 1}

        cleaner.skill(_register_skill("p2", _parse))
        cleaner.skill(_register_skill("i2", _index))
        cleaner.job(
            register_agent_job(
                _job([
                    AgentStepDef(id="parse", skill="tst.p2", fan_out="documents", on_error="collect"),
                    AgentStepDef(
                        id="index", skill="tst.i2", depends_on=["parse"],
                        fan_out="documents", skip_if="parse.degraded == true",
                        consume={"blocks": "parse.blocks"},
                    ),
                ], key="ingest_fail_test"),
            )
        )
        outcome = await AgentJobService().submit(
            "sys.ingest_fail_test",
            {"documents": [{"document_id": "a_ok"}, {"document_id": "b_broken"}]},
            SkillContext(user_id="pytest-user", entry="debug"),
            mode="inline",
        )
        # collect: 部分失败不中止, job 成功(失败明细在 steps_state)
        assert outcome["status"] == "succeeded"
        assert recorded_index == ["a_ok"]
        run = await AgentJobService().get(outcome["job_run_id"])
        assert run.steps_state["parse"]["items"]["b_broken"]["status"] == "failed"
        assert run.steps_state["index"]["items"]["b_broken"]["status"] == "skipped"
        assert "dependency_failed" in run.steps_state["index"]["items"]["b_broken"]["reason"]

    async def test_when_skips_whole_step(self, cleaner):
        """步骤级准入 when: 表达式为假整步跳过(判定结果落库)"""
        recorded: list[str] = []

        async def _first(skill_input, ctx, caps, progress):
            return {"ok": True}

        async def _second(skill_input, ctx, caps, progress):
            recorded.append(str(skill_input["document_id"]))
            return {"ok": True}

        cleaner.skill(_register_skill("w1", _first))
        cleaner.skill(_register_skill("w2", _second))
        cleaner.job(
            register_agent_job(
                _job([
                    AgentStepDef(id="first", skill="tst.w1", fan_out="documents"),
                    AgentStepDef(
                        id="second", skill="tst.w2", depends_on=["first"],
                        when="first.failed > 0",  # first 无失败 → 恒 False → 整步跳过
                    ),
                ], key="ingest_when_test"),
            )
        )
        outcome = await AgentJobService().submit(
            "sys.ingest_when_test",
            {"documents": [{"document_id": "d1"}]},
            SkillContext(user_id="pytest-user", entry="debug"),
            mode="inline",
        )
        assert outcome["status"] == "succeeded"
        assert recorded == []
        run = await AgentJobService().get(outcome["job_run_id"])
        assert run.steps_state["second"]["status"] == "skipped"
        assert run.steps_state["second"]["when"] == {"expr": "first.failed > 0", "result": False}
