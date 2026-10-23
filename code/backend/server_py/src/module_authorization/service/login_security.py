"""登录安全策略服务(REQ-014): 登录失败锁定 / 密码强度校验

- 失败计数走缓存(Fakeredis/Redis 双适配), 无新表无迁移, 无常驻内存态
- 计数键 TTL 即锁定窗口: 最后一次失败起算 lock_minutes, 到期键过期自动恢复
- 参数全部来自动态配置 login_security 组(管理员通用配置页可调, 即时生效)
- 缓存不可用时降级放行(仅告警不阻断认证, 与令牌黑名单降级策略一致)
"""

import logging
import re

from common.config.db import db_cache
from common.config.dynamic.schemas import LoginSecuritySettings

logger = logging.getLogger(__name__)

# 登录失败计数键(模块前缀+业务隔离, 仿 contact:code:{scene}:{target} 命名惯例)
LOGIN_FAIL_KEY = "auth:login:fail:{username}"

# 密码字符类别(小写/大写/数字/特殊字符)
_LOWER_RE = re.compile(r"[a-z]")
_UPPER_RE = re.compile(r"[A-Z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^a-zA-Z0-9]")


def password_policy_error(password: str, cfg: LoginSecuritySettings) -> str | None:
    """纯函数: 按密码策略校验, 通过返回 None, 不通过返回错误消息(前后端共用文案来源)"""
    if len(password) < cfg.password_min_length:
        return f"密码长度至少 {cfg.password_min_length} 位"
    classes = sum(
        (
            bool(_LOWER_RE.search(password)),
            bool(_UPPER_RE.search(password)),
            bool(_DIGIT_RE.search(password)),
            bool(_SPECIAL_RE.search(password)),
        )
    )
    if classes < cfg.password_require_classes:
        return (
            f"密码需至少包含 {cfg.password_require_classes} 种字符类别"
            "(小写字母/大写字母/数字/特殊字符)"
        )
    return None


class LoginSecurityService:
    """登录失败锁定与密码强度策略(无状态, 读缓存与动态配置)"""

    async def _get_fail_count(self, username: str) -> int:
        saved = await db_cache.async_cache.get(LOGIN_FAIL_KEY.format(username=username))
        # redis 客户端可能返回 bytes, 统一按字符串处理
        if isinstance(saved, bytes):
            saved = saved.decode()
        return int(saved or 0)

    async def check_lock(self, username: str, cfg: LoginSecuritySettings) -> None:
        """锁定期内直接拒绝(不计新失败), 提示剩余时间
        :raises: ValueError 如果账户处于锁定期
        """
        try:
            count = await self._get_fail_count(username)
            if count < cfg.max_failed_attempts:
                return
            ttl = await db_cache.async_cache.ttl(LOGIN_FAIL_KEY.format(username=username))
            minutes = max(1, -(-max(ttl, 1) // 60))  # 向上取整, 至少提示 1 分钟
            raise ValueError(f"登录失败次数过多, 账户已锁定, 请约 {minutes} 分钟后再试")
        except ValueError:
            raise
        except Exception as e:
            # 缓存不可用时降级放行(可用性优先, 不因锁定组件故障阻断全部登录)
            logger.warning(f"登录失败锁定缓存不可用, 跳过锁定检查: {e}")

    async def record_failure(self, username: str, cfg: LoginSecuritySettings) -> None:
        """记录一次登录失败: 计数 +1(封顶避免溢出), 刷新锁定窗口 TTL"""
        try:
            key = LOGIN_FAIL_KEY.format(username=username)
            count = min(await self._get_fail_count(username) + 1, cfg.max_failed_attempts)
            await db_cache.async_cache.set(key, str(count), ex=cfg.lock_minutes * 60)
        except Exception as e:
            logger.warning(f"登录失败计数写入失败(降级忽略): {e}")

    async def clear_failures(self, username: str) -> None:
        """登录成功后清空失败计数"""
        try:
            await db_cache.async_cache.delete(LOGIN_FAIL_KEY.format(username=username))
        except Exception as e:
            logger.warning(f"登录失败计数清理失败(降级忽略): {e}")
