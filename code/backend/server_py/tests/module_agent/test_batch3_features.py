"""REQ-018 批次 3 测试: script 沙箱(逃逸边界) / Skill Hub 包加载 / MCP adapter / 计费口径"""

import json
import zipfile
from io import BytesIO

import pytest

from module_agent.service import skill_runtime as sr
from module_agent.skills.registry import SKILL_REGISTRY


def _py(code: str) -> str:
    return "import sys, json\n" + code


class TestScriptSandbox:
    """沙箱执行与逃逸边界(§9 批次 3 验收: 沙箱逃逸测试通过)"""

    async def test_success_json_roundtrip(self):
        from module_agent.service.script_sandbox import execute_in_sandbox

        result = await execute_in_sandbox(
            "python",
            _py("data = json.load(sys.stdin); print(json.dumps({'echo': data['x'] * 2}))"),
            {"x": 21},
        )
        assert result == {"echo": 42}

    async def test_env_is_cleared(self):
        """逃逸边界: 环境变量白名单外不可见(密钥不泄漏进沙箱)"""
        import os

        from module_agent.service.script_sandbox import execute_in_sandbox

        os.environ["SANDBOX_SECRET_FOR_TEST"] = "leak-me"
        try:
            result = await execute_in_sandbox(
                "python",
                _py("print(json.dumps({'secret': os.environ.get('SANDBOX_SECRET_FOR_TEST')}))")
                .replace("import sys, json", "import sys, json, os"),
                {},
            )
            assert result["secret"] is None
        finally:
            os.environ.pop("SANDBOX_SECRET_FOR_TEST", None)

    async def test_timeout_kills_process(self):
        from module_agent.service.script_sandbox import SandboxViolationError, execute_in_sandbox

        with pytest.raises(SandboxViolationError, match="超时"):
            await execute_in_sandbox(
                "python", "import time; time.sleep(30)", {}, timeout_s=1
            )

    async def test_nonzero_exit_is_permanent(self):
        from module_agent.service.script_sandbox import SandboxViolationError, execute_in_sandbox

        with pytest.raises(SandboxViolationError, match="退出码"):
            await execute_in_sandbox("python", "import sys; sys.exit(3)", {})

    async def test_bash_interpreter(self):
        from module_agent.service.script_sandbox import execute_in_sandbox

        payload = json.dumps({"input": "abcd"})
        result = await execute_in_sandbox(
            "bash", "read line; echo ${#line}", {"input": "abcd"}
        )
        # 纯数字输出非 JSON → 走 text 通道(JSON 路径由 python 用例覆盖)
        assert int(result["text"]) == len(payload)

    async def test_path_traversal_blocked(self):
        from module_agent.service.script_sandbox import SandboxViolationError, execute_in_sandbox

        with pytest.raises(SandboxViolationError, match="越界"):
            await execute_in_sandbox(
                "python", "print('{}')", {}, extra_files={"../escape.txt": "x"}
            )


def _build_package_zip(name: str = "demo_pack") -> bytes:
    """构造社区 SKILL.md 包 zip(frontmatter + 指令 + 脚本 + references)"""
    skill_md = (
        "---\n"
        f"name: {name}\n"
        "version: 1.2.0\n"
        "description: 测试社区包\n"
        "---\n"
        "你是数据整理助手, 按用户要求整理输入: {{input}}\n"
    )
    script = _py("data = json.load(sys.stdin); print(json.dumps({'word_count': len(str(data['input']).split())}))")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SKILL.md", skill_md)
        z.writestr("scripts/word_count.py", script)
        z.writestr("references/style.md", "# 风格指南\n正式书面语。")
    return buf.getvalue()


async def _purge_namespace(namespace: str) -> None:
    """清理指定命名空间的 DB 残留行(失败重跑/脏数据防护)"""
    from common.config.db import db_manager
    from module_agent.do.skill import AiSkill, AiSkillVersion
    from sqlmodel import select

    async with db_manager.db_rel.session_factory() as session:
        rows = (
            await session.exec(select(AiSkill).where(AiSkill.namespace == namespace))
        ).all()
        for row in rows:
            versions = (
                await session.exec(
                    select(AiSkillVersion).where(AiSkillVersion.skill_id == row.id)
                )
            ).all()
            for v in versions:
                await session.delete(v)
            await session.delete(row)
        await session.commit()
        for row in rows:
            SKILL_REGISTRY.pop(row.key, None)
            sr._impl_cache.pop(f"skill_hub:{row.key}", None)
            sr._impl_cache.pop(f"mcp_adapter:{row.key}", None)


class TestSkillHub:
    """SKILL.md 包加载器: 拆解注册/沙箱执行/渐进式披露/恢复/删除"""

    async def test_import_invoke_and_trace(self):
        from module_agent.service.skill_hub import SkillHubService
        from module_agent.service.skill_runtime import SkillContext, SkillRuntime

        service = SkillHubService()
        await _purge_namespace("pack.demo_pack")
        outcome = await service.import_package(_build_package_zip(), "pytest-user")
        assert outcome["namespace"] == "pack.demo_pack"
        assert set(outcome["skills"]) == {"pack.demo_pack.main", "pack.demo_pack.word_count"}
        try:
            # 指令 Skill: 渐进式披露(references 清单注入模板)
            main = SKILL_REGISTRY["pack.demo_pack.main"]
            assert main.skill_type == "prompt" and main.agent_callable is True
            assert "references/style.md" in main.prompt["template"]
            # 脚本 Skill: 沙箱执行 + 默认不暴露对话
            script_manifest = SKILL_REGISTRY["pack.demo_pack.word_count"]
            assert script_manifest.skill_type == "python_script"
            assert script_manifest.agent_callable is False
            envelope = await SkillRuntime().invoke(
                "pack.demo_pack.word_count",
                {"input": "one two three four"},
                SkillContext(user_id="pytest-user", entry="debug"),
            )
            assert envelope["status"] == "succeeded"
            assert envelope["result"]["word_count"] == 4
            assert envelope["result"]["meta"]["sandbox"]["isolated"] is True
            # 可追溯(§9 验收: 注册后调用且 skill_invocation 可追溯)
            row = await SkillRuntime().get_invocation(envelope["invocation_id"])
            assert row is not None and row.skill_key == "pack.demo_pack.word_count"
        finally:
            await service.remove_package("pack.demo_pack", "pytest-user")
        assert "pack.demo_pack.main" not in SKILL_REGISTRY
        assert "pack.demo_pack.word_count" not in SKILL_REGISTRY

    async def test_rejects_bad_zip(self):
        from module_agent.service.skill_hub import SkillHubService
        from common.utils.fastapi_ex.exceptions import BusinessError

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("README.md", "no skill md")
        with pytest.raises(BusinessError, match="SKILL.md"):
            await SkillHubService().import_package(buf.getvalue(), "pytest-user")

    async def test_restore_from_db(self):
        from module_agent.service.skill_hub import (
            SkillHubService,
            restore_skill_hub_packages,
        )

        service = SkillHubService()
        await _purge_namespace("pack.restore_pack")
        await service.import_package(_build_package_zip("restore_pack"), "pytest-user")
        try:
            # 模拟重启: 反注册 → 从 DB 恢复
            for uid in ("pack.restore_pack.main", "pack.restore_pack.word_count"):
                SKILL_REGISTRY.pop(uid, None)
                sr._impl_cache.pop(f"skill_hub:{uid}", None)
            stats = await restore_skill_hub_packages()
            assert stats["restored"] >= 2
            assert "pack.restore_pack.main" in SKILL_REGISTRY
            assert "skill_hub:pack.restore_pack.word_count" in sr._impl_cache
        finally:
            await service.remove_package("pack.restore_pack", "pytest-user")


_MCP_TEST_SERVER = """
import sys, json
for line in sys.stdin:
    try:
        msg = json.loads(line)
    except Exception:
        continue
    method = msg.get("method")
    if method == "initialize":
        resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-server", "version": "1"}}}
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [{
            "name": "getWeather", "description": "查询城市天气",
            "inputSchema": {"type": "object", "required": ["city"],
                            "properties": {"city": {"type": "string"}}}}]}}
    elif method == "tools/call":
        city = (msg.get("params") or {}).get("arguments", {}).get("city", "?")
        resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
            "content": [{"type": "text", "text": f"{city}: 晴 25C"}]}}
    else:
        continue
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""


class TestMcpAdapter:
    """MCP adapter 反射注册(§9 验收: MCP tools 注册后可调用且可追溯)"""

    async def test_register_invoke_and_trace(self, tmp_path):
        from module_agent.service.mcp_adapter import McpServerService
        from module_agent.service.skill_runtime import SkillContext, SkillRuntime

        server_script = tmp_path / "mcp_test_server.py"
        server_script.write_text(_MCP_TEST_SERVER, encoding="utf-8")
        service = McpServerService()
        await _purge_namespace("mcp.weathertest")
        outcome = await service.register(
            {
                "name": "weathertest",
                "command": "python3",
                "args": [str(server_script)],
            },
            "pytest-user",
        )
        # 工具名规范化: getWeather → getweather
        assert outcome["tools"] == ["mcp.weathertest.getweather"]
        try:
            manifest = SKILL_REGISTRY["mcp.weathertest.getweather"]
            assert manifest.skill_type == "mcp_tool"
            assert manifest.input_schema["required"] == ["city"]
            envelope = await SkillRuntime().invoke(
                "mcp.weathertest.getweather",
                {"city": "北京"},
                SkillContext(user_id="pytest-user", entry="debug"),
            )
            assert envelope["status"] == "succeeded"
            assert envelope["result"]["text"] == "北京: 晴 25C"
            row = await SkillRuntime().get_invocation(envelope["invocation_id"])
            assert row is not None and row.skill_key == "mcp.weathertest.getweather"
        finally:
            await service.remove("mcp.weathertest")
        assert "mcp.weathertest.getweather" not in SKILL_REGISTRY

    async def test_register_rejects_unreachable_server(self):
        from common.utils.fastapi_ex.exceptions import BusinessError
        from module_agent.service.mcp_adapter import McpServerService

        with pytest.raises(BusinessError, match="连接/握手失败"):
            await McpServerService().register(
                {"name": "dead", "command": "definitely-not-a-command-xyz"}, "pytest-user"
            )
