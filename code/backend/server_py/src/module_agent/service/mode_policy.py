"""两级模式解析器(模式即 Agent, REQ-019 设计 §2.2)

**纯函数, 无 IO, 可单测**: 输入 = 请求模式 + 意图信号 + 工具可用性,
输出 = 执行模式 + 决策理由(前端可见, AG-UI `rag.mode_decision`)。

两级模式(设计 §2.2):
- `requested_mode`: 用户选择(auto / fast / thinking)
- `exec_mode`: 实际执行模式(fast / thinking / deep)

设计 §2.2 的解析表:

| requested | 意图信号          | 工具可用性          | exec_mode |
|-----------|-------------------|---------------------|-----------|
| auto      | 简单单问          | 任意                | fast      |
| auto      | 复合/需交叉验证   | 有知识库或联网      | deep      |
| auto      | 复合/需交叉验证   | 无任何可用工具      | thinking  |
| fast      | 任意              | 任意                | fast      |
| thinking  | 任意              | 有可用工具          | thinking  |
| thinking  | 强信号            | 有可用工具          | deep      |
| thinking  | 任意              | 无可用工具          | thinking  |

硬规则(设计 §2.2):
1. 纯函数、无 IO;
2. 必须产出 `mode_reason`(前端展示"本次为什么用深度思考");
3. 降级必须显式: 工具不可用时不得进 deep;
4. 用户显式选择的模式不得被自动升级(fast 不升 deep; 自动升级只发生在 auto)。
"""

from enum import StrEnum
from dataclasses import dataclass, field

from module_agent.agents.builtin import ChatModeConfig


class RequestedMode(StrEnum):
    """用户请求的模式"""

    AUTO = "auto"
    FAST = "fast"
    THINKING = "thinking"


class ExecMode(StrEnum):
    """实际执行模式(deep 是 thinking Agent 内的升级档, 不是第三个 Agent)"""

    FAST = "fast"
    THINKING = "thinking"
    DEEP = "deep"


class IntentSignal(StrEnum):
    """意图信号(设计 §2.2)"""

    SIMPLE = "simple"              # 简单单问
    COMPLEX = "complex"            # 复合问题
    CROSS_SOURCE = "cross_source"  # 需要多源交叉
    EXPLICIT_DEEP = "explicit_deep"  # 显式要求"深度思考"
    HISTORY_FALLBACK = "history_fallback"  # 历史轮次回退意图
    STRONG = "strong"              # 强信号(触发 deep)


@dataclass(frozen=True)
class ModeSignals:
    """意图信号集合"""

    signals: frozenset[str] = field(default_factory=frozenset)

    def has(self, signal: str) -> bool:
        return signal in self.signals

    @property
    def is_complex(self) -> bool:
        """复合问题或需多源交叉"""
        return bool(
            self.signals
            & {IntentSignal.COMPLEX.value, IntentSignal.CROSS_SOURCE.value}
        )

    @property
    def is_strong(self) -> bool:
        """强信号: 显式深度 / 多源交叉失败 / 历史回退"""
        return bool(
            self.signals
            & {
                IntentSignal.EXPLICIT_DEEP.value,
                IntentSignal.CROSS_SOURCE.value,
                IntentSignal.HISTORY_FALLBACK.value,
            }
        )


@dataclass(frozen=True)
class ToolAvailability:
    """工具可用性(决定是否允许进入 deep)"""

    has_kb: bool = False       # 有可用知识库
    has_web: bool = False      # 已开启联网
    has_sandbox: bool = False  # 沙箱已启用且配置完整

    @property
    def any_tool(self) -> bool:
        """是否有任何可调用工具"""
        return self.has_kb or self.has_web or self.has_sandbox

    @property
    def can_deep(self) -> bool:
        """deep 档必须有工具可调, 否则预算白白消耗"""
        return self.has_kb or self.has_web or self.has_sandbox


@dataclass(frozen=True)
class ModeDecision:
    """模式解析结果"""

    exec_mode: ExecMode
    mode_reason: str
    requested_mode: RequestedMode
    config: ChatModeConfig


def resolve_mode(
    requested_mode: str,
    signals: ModeSignals,
    tools: ToolAvailability,
    config_of: "callable[[str], ChatModeConfig | None]",
) -> ModeDecision:
    """解析执行模式(纯函数)

    Args:
        requested_mode: 用户请求的模式(auto/fast/thinking)
        signals: 意图信号
        tools: 工具可用性
        config_of: 取某档位运行参数的回调(内置 Agent chat_modes / 平台配置 / 默认值)

    Returns:
        ModeDecision: 执行模式 + 决策理由 + 运行参数
    """
    requested = _normalize_requested(requested_mode)

    if requested is RequestedMode.FAST:
        # 规则 4: 用户显式选择 fast, 不得被自动升级
        exec_mode = ExecMode.FAST
        reason = "用户显式选择快速模式, 不做自动升级"
    elif requested is RequestedMode.THINKING:
        if tools.any_tool and signals.is_strong:
            exec_mode = ExecMode.DEEP
            reason = "用户选择思考模式且命中强信号, 升级为深度执行"
        elif tools.any_tool:
            exec_mode = ExecMode.THINKING
            reason = "用户显式选择思考模式, 保持思考档"
        else:
            # 规则 3: 无可用工具 → 显式降级, 只检索+自答
            exec_mode = ExecMode.THINKING
            reason = "无可用工具, 深度执行无意义, 降级为仅检索+自答"
    else:  # auto
        if not signals.is_complex:
            exec_mode = ExecMode.FAST
            reason = "简单单问, 自动选择快速模式"
        elif tools.can_deep:
            exec_mode = ExecMode.DEEP
            reason = "复合问题且工具齐备, 自动升级为深度执行"
        else:
            exec_mode = ExecMode.THINKING
            reason = "复合问题但无任何可用工具, 降级为多轮检索补查, 不进工具循环"

    config = config_of(exec_mode.value)
    if config is None:  # 配置全缺失时用硬编码默认值兜底(设计 §2.1 三级回退)
        from module_agent.agents.builtin import mode_defaults

        config = ChatModeConfig(**mode_defaults()[exec_mode.value])

    return ModeDecision(
        exec_mode=exec_mode,
        mode_reason=reason,
        requested_mode=requested,
        config=config,
    )


def _normalize_requested(raw: str | None) -> RequestedMode:
    """归一化请求模式; 非法值按 auto 处理"""
    if not raw:
        return RequestedMode.AUTO
    try:
        return RequestedMode(raw)
    except ValueError:
        return RequestedMode.AUTO
