"""REQ-018 批次 2 测试: 队列路由 / prompt 自定义 Skill / 断点续跑"""

import pytest

from module_agent.service import skill_runtime as sr
from module_agent.skills.registry import SKILL_REGISTRY


class TestQueueRouting:
    """物理队列拆分: priority>=7 → q_interactive(B2-1)"""

    def test_interactive_routes_to_dedicated_queue(self, monkeypatch):
        import module_agent.tasks  # noqa: F401 (注册 skill_execute/agent_job_execute)
        import module_task.tasks as mt
        from common.config.tasks import DEFAULT_QUEUE, INTERACTIVE_QUEUE

        sent: list[dict] = []

        class _FakeResult:
            id = "celery-fake-id"

        def _fake_send_task(name, args=None, queue=None, priority=None):
            # Celery send_task 是同步 API(返回 AsyncResult), fake 保持同步
            sent.append({"name": name, "args": args, "queue": queue, "priority": priority})
            return _FakeResult()

        monkeypatch.setattr(
            "common.config.tasks.app",
            type("FakeApp", (), {"send_task": staticmethod(_fake_send_task)}),
        )

        class _FakeTask:
            def __init__(self, priority):
                self.id = "t1"
                self.priority = priority

        async def _go():
            await mt.dispatch_task(_FakeTask(7), mt.TASK_TYPES["skill_execute"])
            await mt.dispatch_task(_FakeTask(5), mt.TASK_TYPES["skill_execute"])
            await mt.dispatch_task(_FakeTask(9), mt.TASK_TYPES["agent_job_execute"])

        import asyncio

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_go())
        assert sent[0]["queue"] == INTERACTIVE_QUEUE  # 会话交互类 → 独立队列
        assert sent[1]["queue"] == DEFAULT_QUEUE      # 常规 → 默认队列
        assert sent[2]["queue"] == INTERACTIVE_QUEUE


class TestPromptSkill:
    """自定义 prompt Skill: 状态机 + 注册联动 + 内建执行器(B2-3)"""

    async def test_template_rendering(self):
        from module_agent.service.prompt_skill import _render_template

        template = "把这段话翻译成英文: {{text}}。语气: {{tone}}"
        out = _render_template(template, {"text": "你好", "tone": "正式"})
        assert out == "把这段话翻译成英文: 你好。语气: 正式"
        # 未知字段保留原样(便于提示词示例花括号)
        out2 = _render_template("示例 {{unknown}}", {})
        assert out2 == "示例 {{unknown}}"

    async def test_lifecycle_publish_invoke_deprecate(self, monkeypatch):
        from module_agent.service.prompt_skill import (
            PromptFieldDef,
            PromptSkillCreate,
            PromptSkillService,
        )
        from module_rag.service.user_model import UserModelService

        calls: list[str] = []

        class _FakeLLM:
            async def ainvoke(self, messages):
                calls.append(messages[0].content)
                return type("Msg", (), {"content": "翻译结果: hello"})()

        async def _get_llm(self, user_id, streaming=True, model_type=None):
            return _FakeLLM()

        monkeypatch.setattr(UserModelService, "get_llm_by_user_id", _get_llm)

        service = PromptSkillService()
        key = f"trans_{id(self)}_{calls.__len__()}" [:40]
        created = await service.create(
            PromptSkillCreate(
                key=key,
                name="翻译助手",
                template="把这段话翻译成英文: {{text}}",
                fields=[PromptFieldDef(name="text", type="string")],
            ),
            user_id="pytest-user",
        )
        skill_id = created["skill_id"]
        uid = created["key"]
        try:
            # draft 状态不注册不可调用
            assert SKILL_REGISTRY.get(uid) is None

            # 发布 → 注册表可见
            await service.publish(skill_id, "pytest-user")
            assert SKILL_REGISTRY.get(uid) is not None
            manifest = SKILL_REGISTRY[uid]
            assert manifest.skill_type == "prompt" and manifest.required_capabilities == ["chat"]

            # 三入口同一实现: 经 SkillRuntime invoke(inline)
            from module_agent.service.skill_runtime import SkillContext, SkillRuntime

            envelope = await SkillRuntime().invoke(
                uid, {"text": "你好"}, SkillContext(user_id="pytest-user", entry="debug")
            )
            assert envelope["status"] == "succeeded"
            assert envelope["result"]["text"] == "翻译结果: hello"
            assert "你好" in calls[0]  # 模板已渲染

            # 下线 → 反注册, 新调用被拒
            await service.deprecate(skill_id, "pytest-user")
            assert SKILL_REGISTRY.get(uid) is None
            envelope2 = await SkillRuntime().invoke(
                uid, {"text": "x"}, SkillContext(user_id="pytest-user", entry="debug")
            )
            assert envelope2["status"] == "failed"
        finally:
            SKILL_REGISTRY.pop(uid, None)
            sr._impl_cache.pop(f"prompt_skill:{uid}", None)
            # 清理 DB 行
            from common.config.db import db_manager
            from module_agent.do.skill import AiSkill, AiSkillVersion
            from sqlmodel import select

            async with db_manager.db_rel.session_factory() as session:
                row = await session.get(AiSkill, skill_id)
                if row is not None:
                    versions = (
                        await session.exec(
                            select(AiSkillVersion).where(AiSkillVersion.skill_id == skill_id)
                        )
                    ).all()
                    for v in versions:
                        await session.delete(v)
                    await session.delete(row)
                    await session.commit()

    async def test_restore_after_restart(self, monkeypatch):
        """启动恢复: published 的 prompt Skill 从 DB 重建注册(含 impl 闭包)"""
        from module_agent.service.prompt_skill import (
            PromptFieldDef,
            PromptSkillCreate,
            PromptSkillService,
            restore_custom_prompt_skills,
        )
        from module_rag.service.user_model import UserModelService

        async def _get_llm(self, user_id, streaming=True, model_type=None):
            return None  # 恢复只验注册, 不真实调用

        monkeypatch.setattr(UserModelService, "get_llm_by_user_id", _get_llm)

        service = PromptSkillService()
        created = await service.create(
            PromptSkillCreate(
                key=f"restore_{id(self)}"[:40],
                name="恢复测试",
                template="总结: {{input}}",
            ),
            user_id="pytest-user",
        )
        skill_id, uid = created["skill_id"], created["key"]
        try:
            await service.publish(skill_id, "pytest-user")
            # 模拟重启: 反注册后从 DB 恢复
            SKILL_REGISTRY.pop(uid, None)
            sr._impl_cache.pop(f"prompt_skill:{uid}", None)
            stats = await restore_custom_prompt_skills()
            assert stats["restored"] >= 1
            assert SKILL_REGISTRY.get(uid) is not None
            assert f"prompt_skill:{uid}" in sr._impl_cache
        finally:
            SKILL_REGISTRY.pop(uid, None)
            sr._impl_cache.pop(f"prompt_skill:{uid}", None)
            from common.config.db import db_manager
            from module_agent.do.skill import AiSkill, AiSkillVersion
            from sqlmodel import select

            async with db_manager.db_rel.session_factory() as session:
                row = await session.get(AiSkill, skill_id)
                if row is not None:
                    versions = (
                        await session.exec(
                            select(AiSkillVersion).where(AiSkillVersion.skill_id == skill_id)
                        )
                    ).all()
                    for v in versions:
                        await session.delete(v)
                    await session.delete(row)
                    await session.commit()


class TestJobResume:
    """断点续跑: 已成功项复用, 失败项重跑(B2-4)"""

    async def test_resume_skips_succeeded_items(self):
        from module_agent.agents.manifest import AgentJobManifest, AgentStepDef, register_agent_job
        from module_agent.agents import AGENT_JOBS
        from module_agent.service.agent_job import AgentJobService
        from module_agent.service.skill_runtime import SkillContext
        from module_agent.skills.manifest import ExecutionSpec, SkillManifest
        from module_agent.skills.registry import register_skill

        parse_calls: list[str] = []

        async def _parse(skill_input, ctx, caps, progress):
            doc = str(skill_input["document_id"])
            parse_calls.append(doc)
            if doc == "bad":
                raise ValueError("解析失败")
            return {"blocks": [{"content": "b"}], "meta": {}}

        async def _index(skill_input, ctx, caps, progress):
            return {"chunk_count": 1}

        manifests = []
        for key, fn in (("resume_parse", _parse), ("resume_index", _index)):
            m = SkillManifest(
                namespace="tst", key=key, name=f"测-{key}", description="d",
                impl_ref=f"tst.resume:{key}",
                input_schema={"type": "object", "required": ["document_id"],
                              "properties": {"document_id": {"type": "string"}}},
                output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                execution=ExecutionSpec(modes=["inline"], inline_timeout_s=5),
            )
            register_skill(m)
            sr._impl_cache[m.impl_ref] = fn
            manifests.append(m)
        job = AgentJobManifest(
            key="resume_test",
            name="续跑测试",
            description="d",
            steps=[
                AgentStepDef(id="parse", skill="tst.resume_parse", fan_out="documents", on_error="collect"),
                AgentStepDef(
                    id="index", skill="tst.resume_index", depends_on=["parse"],
                    fan_out="documents", consume={"blocks": "parse.blocks"},
                ),
            ],
        )
        register_agent_job(job)
        service = AgentJobService()
        try:
            # 第一次: ok 成功, bad 失败(collect 不中止, job 状态 failed)
            outcome = await service.submit(
                "sys.resume_test",
                {"documents": [{"document_id": "ok"}, {"document_id": "bad"}]},
                SkillContext(user_id="pytest-user", entry="debug"),
                mode="inline",
            )
            assert outcome["status"] == "succeeded"  # collect 语义
            assert parse_calls.count("ok") == 1 and parse_calls.count("bad") == 1
            run = await service.get(outcome["job_run_id"])
            assert run.steps_state["parse"]["items"]["bad"]["status"] == "failed"
            assert run.checkpoint.get("artifacts", {}).get("parse", {}).get("ok", {}).get("result") is not None

            # 手工置失败态以触发续跑(collect 语义下 job 是 succeeded, 模拟中断场景)
            from module_agent.do.agent_job_run import JobRunStatus
            from common.config.db import db_manager

            async with db_manager.db_rel.session_factory() as session:
                row = await service.get(outcome["job_run_id"])
                from sqlalchemy import update as sa_update
                from module_agent.do.agent_job_run import AgentJobRun

                async with session.begin():
                    await session.execute(
                        sa_update(AgentJobRun)
                        .where(AgentJobRun.job_run_id == row.job_run_id)
                        .values(status=JobRunStatus.FAILED)
                    )

            # 续跑: ok 已成功不重复执行, bad 重跑
            resumed = await service.resume_run(row.job_run_id, "pytest-user")
            assert resumed["status"] == "succeeded"
            assert parse_calls.count("ok") == 1      # 未重复
            assert parse_calls.count("bad") == 2     # 重跑一次
            run2 = await service.get(row.job_run_id)
            assert run2.steps_state["parse"]["items"]["ok"].get("resumed") is True
        finally:
            for m in manifests:
                SKILL_REGISTRY.pop(m.uid, None)
                sr._impl_cache.pop(m.impl_ref, None)
            AGENT_JOBS.pop(job.agent_key, None)
