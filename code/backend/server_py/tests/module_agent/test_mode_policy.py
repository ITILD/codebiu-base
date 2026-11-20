"""两级模式解析器单测(REQ-019 设计 §2.2)

纯函数验证: 不依赖 DB / lifespan, 覆盖设计 §2.2 解析表 7 个场景 + 硬规则。
"""

import pytest

from module_agent.agents.builtin import ChatModeConfig, resolve_mode_config
from module_agent.service.mode_policy import (
    ExecMode,
    IntentSignal,
    ModeSignals,
    RequestedMode,
    ToolAvailability,
    resolve_mode,
)


def _sig(*names: str) -> ModeSignals:
    return ModeSignals(signals=frozenset(names))


# 简单的档位配置回调(不依赖内置 Agent, 便于断言透传)
def _cfg_of(mode: str):
    return ChatModeConfig(max_loops=2, wall_clock_s=30) if mode in ("fast", "thinking", "deep") else None


# ── 设计 §2.2 解析表: 7 场景逐行验证 ─────────────────────────────


@pytest.mark.parametrize(
    "requested, signals, tools, expected",
    [
        # 1. auto + 简单单问 → fast(任意工具可用性)
        ("auto", _sig(IntentSignal.SIMPLE.value), ToolAvailability(has_kb=True), ExecMode.FAST),
        ("auto", _sig(), ToolAvailability(), ExecMode.FAST),
        # 2. auto + 复合 + 有工具 → deep
        (
            "auto",
            _sig(IntentSignal.COMPLEX.value),
            ToolAvailability(has_kb=True),
            ExecMode.DEEP,
        ),
        (
            "auto",
            _sig(IntentSignal.CROSS_SOURCE.value),
            ToolAvailability(has_web=True),
            ExecMode.DEEP,
        ),
        # 3. auto + 复合 + 无任何工具 → thinking 显式降级
        (
            "auto",
            _sig(IntentSignal.COMPLEX.value),
            ToolAvailability(),
            ExecMode.THINKING,
        ),
        # 4. fast + 任意 → fast(不被自动升级)
        ("fast", _sig(IntentSignal.EXPLICIT_DEEP.value), ToolAvailability(has_kb=True), ExecMode.FAST),
        # 5. thinking + 普通信号 + 有工具 → thinking
        (
            "thinking",
            _sig(IntentSignal.SIMPLE.value),
            ToolAvailability(has_kb=True),
            ExecMode.THINKING,
        ),
        # 6. thinking + 强信号 + 有工具 → deep
        (
            "thinking",
            _sig(IntentSignal.EXPLICIT_DEEP.value),
            ToolAvailability(has_kb=True, has_web=True),
            ExecMode.DEEP,
        ),
        # 7. thinking + 任意 + 无工具 → thinking(不进 deep)
        ("thinking", _sig(), ToolAvailability(), ExecMode.THINKING),
    ],
)
def test_resolve_mode_table(requested, signals, tools, expected):
    decision = resolve_mode(requested, signals, tools, _cfg_of)
    assert decision.exec_mode is expected
    assert decision.mode_reason  # 规则 2: 必须产出决策理由
    assert decision.config is not None


# ── 硬规则与归一化 ────────────────────────────────────────────────


def test_mode_reason_semantics():
    """决策理由必须区分升级/降级语义(前端展示'为什么是这个模式')"""
    deep = resolve_mode(
        "auto", _sig(IntentSignal.COMPLEX.value), ToolAvailability(has_kb=True), _cfg_of
    )
    assert "深度" in deep.mode_reason
    degraded = resolve_mode(
        "auto", _sig(IntentSignal.COMPLEX.value), ToolAvailability(), _cfg_of
    )
    assert "降级" in degraded.mode_reason


def test_invalid_requested_falls_back_to_auto():
    """非法请求模式按 auto 处理(不抛异常)"""
    decision = resolve_mode("bogus", _sig(), ToolAvailability(has_kb=True), _cfg_of)
    assert decision.requested_mode is RequestedMode.AUTO
    assert decision.exec_mode is ExecMode.FAST


def test_none_requested_is_auto():
    decision = resolve_mode(None, _sig(), ToolAvailability(), _cfg_of)
    assert decision.requested_mode is RequestedMode.AUTO


def test_config_fallback_when_none():
    """配置回调全缺失时用硬编码默认值兜底(设计 §2.1 三级回退), 不崩"""
    decision = resolve_mode(
        "thinking", _sig(IntentSignal.EXPLICIT_DEEP.value), ToolAvailability(has_kb=True),
        lambda _m: None,
    )
    assert decision.exec_mode is ExecMode.DEEP
    assert decision.config.max_loops > 0
    assert decision.config.wall_clock_s > 0


def test_builtin_chat_mode_config_source():
    """内置 Agent 档位: thinking Agent 必须有 thinking/deep 两档, fast 档低预算"""
    thinking_cfg = resolve_mode_config("builtin_thinking", "deep")
    assert thinking_cfg.think_level == "high"
    assert thinking_cfg.max_loops >= 4
    fast_cfg = resolve_mode_config("builtin_fast", "fast")
    assert fast_cfg.think_level == "off"
    assert fast_cfg.wall_clock_s < thinking_cfg.wall_clock_s
