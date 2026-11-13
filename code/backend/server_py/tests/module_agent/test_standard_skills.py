"""标准社区 skill 集成测试(REQ-018: 发现源目录加载 + 官方脚本沙箱端到端)

发现源 = server_py/temp_source/skills/(用户自管理目录, gitignore 内不随仓库
分发): 用户放置含 SKILL.md 的社区包目录即被启动发现加载。本仓库当前预置了
anthropics/skills 官方 docx/pptx/xlsx 三个最受欢迎标准包; 目录为空/不存在时
本模块整体跳过(放哪些包测哪些语义)。
注意: 全程 async 复用 session 事件循环(asyncpg 不跨 loop)。
"""

from pathlib import Path

import pytest

_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "temp_source" / "skills"

pytestmark = pytest.mark.skipif(
    not _SKILLS_ROOT.is_dir() or not any(_SKILLS_ROOT.glob("*/SKILL.md")),
    reason="发现源 temp_source/skills/ 为空或不存在(用户未放置社区包, 跳过集成测试)",
)


@pytest.fixture(scope="module")
async def discovered():
    """发现加载一次(幂等), 模块内共享结果"""
    from module_agent.service.skill_hub import discover_local_packages

    return await discover_local_packages()


class TestPresetDiscovery:
    """预置目录发现加载: 原生结构 → pack.* 拆解注册"""

    def test_three_packages_discovered(self, discovered):
        imported = set(discovered["imported"])
        skipped = set(discovered["skipped"])
        assert {"pack.docx", "pack.pptx", "pack.xlsx"} <= (imported | skipped)
        assert discovered["failed"] == []

    def test_registry_contains_official_skills(self, discovered):
        from module_agent.skills.registry import SKILL_REGISTRY

        # main prompt Skill × 3(SKILL.md 指令即模板, 官方英文触发描述保留)
        for pkg in ("docx", "pptx", "xlsx"):
            main = SKILL_REGISTRY.get(f"pack.{pkg}.main")
            assert main is not None and main.skill_type == "prompt"
            assert main.agent_callable is True
        assert "Word" in SKILL_REGISTRY["pack.docx.main"].description

        # 官方顶层入口脚本 → script 沙箱 Skill(多文件树伴随)
        expected_scripts = {
            "pack.docx.accept_changes", "pack.docx.comment", "pack.docx.merge_runs",
            "pack.pptx.add_slide", "pack.pptx.clean", "pack.pptx.thumbnail",
            "pack.xlsx.recalc",
        }
        for uid in expected_scripts:
            manifest = SKILL_REGISTRY.get(uid)
            assert manifest is not None, f"未注册: {uid}"
            assert manifest.skill_type == "python_script"
            assert manifest.agent_callable is False  # 安全默认: 不直接暴露对话
            files = manifest.script.get("files") or {}
            # 伴随文件 = 官方共享 office 包/模板/Schema(相对 import 可解析的关键;
            # office 为 namespace 包, 不保证有 __init__.py, 以任意 office/ 键为准)
            assert any(k.startswith("office/") for k in files), f"{uid} 缺少伴随 office 共享包"

    async def test_discover_idempotent(self, discovered):
        """重复发现: 已存在跳过, 不重复导入"""
        from module_agent.service.skill_hub import discover_local_packages

        second = await discover_local_packages()
        assert second["imported"] == []
        assert {"pack.docx", "pack.pptx", "pack.xlsx"} <= set(second["skipped"])


class TestOfficialScriptE2E:
    """官方脚本沙箱端到端: 多文件树落盘 → import office 成功 → 执行到参数解析"""

    async def _invoke_comment(self):
        from module_agent.service.skill_runtime import SkillContext, SkillRuntime

        return await SkillRuntime().invoke(
            "pack.docx.comment",
            {"input": ""},
            SkillContext(user_id="pytest-user", entry="debug"),
        )

    async def test_docx_comment_script_reaches_argparse(self):
        """comment.py 空参执行: 若伴随 office 包未落盘会在 import 阶段 ImportError;
        实际执行到 argparse 报 usage(证明共享包/模板树完整可用)"""
        envelope = await self._invoke_comment()
        # 官方脚本为 CLI 形态: 空参 → argparse usage 报错(permanent), 非依赖缺失
        assert envelope["status"] == "failed"
        message = str(envelope.get("error", {}).get("message", ""))
        assert "usage:" in message or "argparse" in message.lower(), message[:300]
        # 关键否定证据: 不是 ImportError(伴随文件树未落盘才会发生)
        assert "ModuleNotFoundError" not in message
        assert "ImportError" not in message

    async def test_invocation_traceable(self):
        """官方 skill 调用可在 skill_invocation 追溯(三入口一致)"""
        from module_agent.skills.registry import SKILL_REGISTRY
        from module_agent.service.skill_runtime import SkillRuntime

        envelope = await self._invoke_comment()
        row = await SkillRuntime().get_invocation(envelope["invocation_id"])
        assert row is not None
        assert row.skill_key == "pack.docx.comment"
        assert row.skill_version == SKILL_REGISTRY["pack.docx.comment"].version
