"""container_ops 运维 Skill 契约单测(REQ-019 §6.2 批次 4-f)

验证: 5 个 sys.container_* Skill 注册齐全 + Manifest 不变量
(static/inline/零重试/幂等键/side_effects 标注/output_schema.properties 非空)
+ ops_agent(sys.ops_worker_heal) 编排清单不变量。不依赖 DB。
"""

import importlib

import pytest

from module_agent.skills.registry import SKILL_REGISTRY, get_skill

# 导入即注册(与运行时一致: module_agent/skills/__init__.py 引入 module_task.skills)
importlib.import_module("module_task.skills.container_ops")

CONTAINER_KEYS = [
    "sys.container_list",
    "sys.container_start",
    "sys.container_stop",
    "sys.container_restart",
    "sys.container_scale_up",
]


@pytest.mark.parametrize("key", CONTAINER_KEYS)
def test_container_skill_registered(key):
    manifest = get_skill(key)
    assert manifest is not None, f"{key} 未注册"
    assert manifest.nature == "static"
    assert manifest.agent_callable is True
    # 全部 inline + 零重试(运维动作失败交编排决策, 不自动重试)
    assert manifest.execution.modes == ["inline"]
    assert manifest.execution.inline_timeout_s > 0
    assert manifest.retry.max == 0
    # 幂等键与 side_effects 标注必备
    assert manifest.idempotency.keys
    assert manifest.side_effects in ("read", "write")
    # CA-03: output_schema.properties 不得为空
    assert manifest.output_schema.get("properties")
    # 输入 schema 形状合法
    assert manifest.input_schema.get("type") == "object"
    assert manifest.input_schema.get("required")


def test_container_list_is_read_only():
    """只有 list 是 read, 其余都是 write(写动作必须显式标注)"""
    assert get_skill("sys.container_list").side_effects == "read"
    for key in CONTAINER_KEYS[1:]:
        assert get_skill(key).side_effects == "write", key


def test_container_list_self_heal_summary_fields():
    """list 产出自愈判定摘要(running/abnormal_count/unhealthy_id)"""
    props = get_skill("sys.container_list").output_schema["properties"]
    for field in ("running", "abnormal_count", "unhealthy_id"):
        assert field in props, field


def test_scale_up_idempotency_covers_host_and_target():
    """幂等键 = host + 目标标识 + 动作语义(设计 §6.2)"""
    assert get_skill("sys.container_list").idempotency.keys == ["host_id", "service"]
    assert get_skill("sys.container_start").idempotency.keys == ["host_id", "container_id"]


# ── ops_agent 编排清单 ───────────────────────────────────────────


def test_ops_worker_heal_manifest_invariants():
    """sys.ops_worker_heal: fan_out 按宿主机展开, 步骤依赖与条件门控齐备"""
    import module_agent.agents.ops as ops  # noqa: F401  导入即注册

    from module_agent.agents.manifest import get_agent_job

    manifest = get_agent_job("sys.ops_worker_heal")
    assert manifest is not None, "ops_worker_heal 未注册"
    manifest.check_invariants()
    assert manifest.decision_mode == "rule"
    steps = {s["id"] if isinstance(s, dict) else s.id: s for s in manifest.steps}

    def step(name: str) -> dict:
        s = steps[name]
        return s if isinstance(s, dict) else s.model_dump()

    # probe → restart → verify → scale_up 线性编排
    assert set(steps) == {"probe", "restart", "verify", "scale_up"}
    # restart: 无异常容器时跳过, 容器 ID 取自 probe 结果
    assert step("restart")["skip_if"] == "probe.abnormal_count == 0"
    assert step("restart")["consume"] == {"container_id": "probe.unhealthy_id"}
    # verify: 依赖 probe(重启被跳过不阻断)
    assert step("verify")["depends_on"] == ["probe"]
    # scale_up: 依赖 verify, 副本已达标即跳过
    assert step("scale_up")["depends_on"] == ["verify"]
    assert step("scale_up")["skip_if"] == "verify.running >= item.expected_replicas"
