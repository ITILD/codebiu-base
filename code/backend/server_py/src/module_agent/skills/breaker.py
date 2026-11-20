"""Skill 会话级熔断器(REQ-019 设计 §5.4)

规则:
- 同一 Skill 在本次会话**连续失败 2 次** → 判定为不可用, 从工具清单摘除并下发
  `skill_masked` 事件, 避免模型在同一坏工具上反复试错烧光预算(CA-12);
- 成功一次即清零连续失败计数(不累计总失败次数);
- 熔断是**会话级**的: 新会话重新评估, 不污染全局。
"""

from collections.abc import Awaitable, Callable
import logging

logger = logging.getLogger(__name__)

#: 连续失败达到该次数即熔断
DEFAULT_FAILURE_THRESHOLD = 2

#: 熔断事件回调(uid, 原因)
MaskCallback = Callable[[str, str], Awaitable[None]]


class SkillCircuitBreaker:
    """会话级 Skill 熔断器"""

    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        on_mask: MaskCallback | None = None,
    ):
        self._threshold = failure_threshold
        self._on_mask = on_mask
        self._consecutive_failures: dict[str, int] = {}
        self._masked: dict[str, str] = {}

    @property
    def masked_uids(self) -> set[str]:
        """已熔断的 Skill 键集合"""
        return set(self._masked.keys())

    def is_masked(self, uid: str) -> bool:
        """该 Skill 是否已被熔断"""
        return uid in self._masked

    def record_success(self, uid: str) -> None:
        """调用成功: 清零连续失败计数"""
        self._consecutive_failures.pop(uid, None)

    async def record_failure(self, uid: str, reason: str = "") -> bool:
        """调用失败: 累计连续失败; 达到阈值则熔断

        :return: 本次调用是否触发了熔断
        """
        count = self._consecutive_failures.get(uid, 0) + 1
        self._consecutive_failures[uid] = count
        if count < self._threshold or uid in self._masked:
            return False
        self._masked[uid] = reason or f"连续失败 {count} 次"
        logger.warning("Skill 已熔断(会话内): %s — %s", uid, self._masked[uid])
        if self._on_mask is not None:
            try:
                await self._on_mask(uid, self._masked[uid])
            except Exception as e:  # 事件下发失败不影响熔断生效
                logger.debug("熔断事件下发失败(忽略): %s", e)
        return True

    def mask_reason(self, uid: str) -> str:
        """熔断原因"""
        return self._masked.get(uid, "")
