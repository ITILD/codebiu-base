"""能力平台 HTTP API 测试(REQ-018 批次 1)

- GET /agent/skills: Manifest 视图一步到位(W-9)
- POST /agent/skills/{key}/invoke: 调试台权限收紧(默认不授予, W 权限表)
- GET /ai/capabilities: 双源能力视图
"""

import pytest


@pytest.fixture
def echo_skill():
    """注册临时 inline 技能供调试台调用(impl 经缓存注入)"""
    from module_agent.service import skill_runtime as sr
    from module_agent.skills.manifest import ExecutionSpec, SkillManifest
    from module_agent.skills.registry import SKILL_REGISTRY, register_skill

    manifest = SkillManifest(
        namespace="tst",
        key="http_echo",
        name="HTTP回声",
        description="API 单测临时技能",
        impl_ref="tst.http_echo:run",
        input_schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"y": {"type": "string"}}},
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=5),
    )
    register_skill(manifest)

    async def _run(skill_input, ctx, caps, progress):
        return {"y": str(skill_input["x"])}

    sr._impl_cache[manifest.impl_ref] = _run
    yield manifest
    SKILL_REGISTRY.pop(manifest.uid, None)
    sr._impl_cache.pop(manifest.impl_ref, None)


class TestSkillApi:
    async def test_list_skills_manifest_view(self, client):
        resp = await client.get("/agent/skills")
        assert resp.status_code == 200
        data = resp.json()
        keys = {item["key"] for item in data}
        assert "sys.doc_parse" in keys
        assert "sys.doc_chunk_index" in keys
        assert "sys.web_search" in keys
        doc_parse = next(i for i in data if i["key"] == "sys.doc_parse")
        # Manifest 契约字段一步到位(W-9)
        assert doc_parse["nature"] == "hybrid"
        assert doc_parse["capabilities"]["optional"] == ["ocr"]
        assert doc_parse["execution"]["modes"] == ["inline", "queued"]

    async def test_invoke_denied_for_normal_user(self, user_client, echo_skill):
        """普通用户无 skill:invoke 权限 → 403(权限默认不授予)"""
        resp = await user_client.post(
            "/agent/skills/tst.http_echo/invoke", json={"input": {"x": "hi"}}
        )
        assert resp.status_code == 403

    async def test_invoke_allowed_for_admin(self, client, echo_skill):
        """管理员(casbin 通配)可调试台直调 → 统一信封"""
        resp = await client.post(
            "/agent/skills/tst.http_echo/invoke", json={"input": {"x": "hi"}}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["result"] == {"y": "hi"}
        assert data["invocation_id"]

    async def test_invoke_observation_traceable(self, client, echo_skill):
        """调用可在 /agent/invocations 追溯(三入口可追溯验收)"""
        invoke_resp = await client.post(
            "/agent/skills/tst.http_echo/invoke", json={"input": {"x": "trace"}}
        )
        invocation_id = invoke_resp.json()["invocation_id"]
        detail = await client.get(f"/agent/invocations/{invocation_id}")
        assert detail.status_code == 200
        assert detail.json()["skill_key"] == "tst.http_echo"
        listing = await client.get("/agent/invocations")
        assert listing.status_code == 200
        assert any(
            i["invocation_id"] == invocation_id for i in listing.json()["items"]
        )

    async def test_jobs_listing(self, client):
        resp = await client.get("/agent/jobs")
        assert resp.status_code == 200
        keys = {j["agent_key"] for j in resp.json()}
        assert "sys.kb_ingest_agent" in keys

    async def test_capabilities_view(self, client):
        resp = await client.get("/ai/capabilities")
        assert resp.status_code == 200
        caps = {c["capability_key"]: c for c in resp.json()}
        assert caps["content_hash"]["kind"] == "static_func"
        assert caps["content_hash"]["available"] is True
        assert caps["chat"]["kind"] == "ai_model"
