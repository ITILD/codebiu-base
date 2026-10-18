"""验证码服务(邮件/短信双通道统一生命周期: 冷却检查/生成/发送/校验)

- 按目标格式自动路由通道: 邮箱 → EmailService, 手机号 → SmsService
- 缓存策略见 config/verify_code.py(60s 冷却, 5min 有效, 校验通过立即失效)
- AuthService(注册验证码)等业务方经依赖注入调用, 业务开关由调用方自行把关
"""
import logging
import re
import secrets

from common.config.db import db_cache
from module_contact.config.verify_code import (
    CODE_COOLDOWN_KEY,
    CODE_COOLDOWN_SECONDS,
    CODE_KEY,
    CODE_LENGTH,
    CODE_TTL_SECONDS,
)
from module_contact.service.email import EmailService, get_email_service
from module_contact.service.sms import SmsService, get_sms_service

logger = logging.getLogger(__name__)

# 通知目标识别: 邮箱 / 大陆手机号
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^1\d{10}$")


class VerifyCodeService:
    """验证码服务(双通道发送 + Redis 生命周期管理)"""

    def __init__(
        self,
        email_service: EmailService | None = None,
        sms_service: SmsService | None = None,
    ):
        """
        :param email_service: 邮件通道(默认取全局单例)
        :param sms_service: 短信通道(默认取全局单例)
        """
        self.email_service = email_service or get_email_service()
        self.sms_service = sms_service or get_sms_service()

    async def send(self, target: str, scene: str = "register") -> bool:
        """发送验证码(先发送成功再落缓存, 失败可直接重试)
        :param target: 通知目标(邮箱或手机号)
        :param scene: 业务场景(缓存键隔离, 如 register/login)
        :return: 是否发送成功
        :raises: ValueError 如果发送过于频繁/目标格式不支持/通道发送失败
        """
        cooldown_key = CODE_COOLDOWN_KEY.format(scene=scene, target=target)
        if await db_cache.async_cache.get(cooldown_key):
            raise ValueError("验证码已发送, 请稍后再试")
        code = f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"
        # 按目标格式自动路由通道
        if _EMAIL_RE.fullmatch(target):
            sent = await self.email_service.send_code(target, code, CODE_TTL_SECONDS // 60)
        elif _PHONE_RE.fullmatch(target):
            sent = await self.sms_service.send_code(target, code, CODE_TTL_SECONDS // 60)
        else:
            raise ValueError("通知目标需为邮箱或手机号")
        if not sent:
            raise ValueError("验证码发送失败, 请稍后重试")
        await db_cache.async_cache.set(
            CODE_KEY.format(scene=scene, target=target), code, ex=CODE_TTL_SECONDS
        )
        await db_cache.async_cache.set(cooldown_key, "1", ex=CODE_COOLDOWN_SECONDS)
        return True

    async def verify(self, target: str, code: str | None, scene: str = "register") -> None:
        """校验验证码(通过后立即失效, 防止重复使用)
        :param target: 通知目标(与发送时一致)
        :param code: 用户提交的验证码
        :param scene: 业务场景(与发送时一致)
        :raises: ValueError 如果验证码缺失或错误/已过期
        """
        if not code:
            raise ValueError("请填写验证码")
        key = CODE_KEY.format(scene=scene, target=target)
        saved = await db_cache.async_cache.get(key)
        # redis 客户端可能返回 bytes, 统一按字符串比较
        if isinstance(saved, bytes):
            saved = saved.decode()
        if not saved or saved != code:
            raise ValueError("验证码错误或已过期")
        await db_cache.async_cache.delete(key)


# 全局单例(无状态, 复用避免重复构造)
_verify_code_service = VerifyCodeService()


def get_verify_code_service() -> VerifyCodeService:
    """VerifyCodeService 依赖注入工厂(FastAPI Depends 使用)"""
    return _verify_code_service
