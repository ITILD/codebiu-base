"""SMTP 邮件服务(依赖 aiosmtplib, 按需读取动态配置)

由 module_authorization 内置实现外置为本模块服务:
- 配置来自动态配置中心 EmailSettings(服务器/端口/发件人/授权码)
- send_code 发送验证码邮件, 供 VerifyCodeService 双通道调度
"""
import logging
from email.message import EmailMessage

import aiosmtplib

from common.config.dynamic import get_settings
from common.config.dynamic.schemas import EmailSettings

logger = logging.getLogger(__name__)


class EmailService:
    """SMTP 邮件服务(异步发送, 按需读取动态配置)"""

    async def _send(self, to_email: str, subject: str, body: str) -> bool:
        """发送纯文本邮件
        :param to_email: 收件邮箱
        :param subject: 邮件主题
        :param body: 纯文本正文
        :return: 是否发送成功(失败仅告警, 由调用方决定提示语)
        """
        cfg = await get_settings(EmailSettings)
        if not cfg.sender_email or not cfg.sender_password:
            logger.warning("邮箱服务未配置(sender_email/sender_password 为空), 跳过发送")
            return False
        msg = EmailMessage()
        msg["From"] = f"{cfg.sender_name} <{cfg.sender_email}>" if cfg.sender_name else cfg.sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            await aiosmtplib.send(
                msg,
                hostname=cfg.smtp_server,
                port=cfg.smtp_port,
                username=cfg.sender_email,
                password=cfg.sender_password,
                use_tls=cfg.smtp_port == 465,  # 465 隐式 SSL, 587 走 STARTTLS
            )
            return True
        except Exception as e:
            logger.error(f"邮件发送失败(to={to_email}): {e}")
            return False

    async def send_code(self, email: str, code: str, ttl_minutes: int) -> bool:
        """发送验证码邮件(邮件/短信双通道统一入口, 场景文案由调用方组织)
        :param email: 收件邮箱
        :param code: 验证码
        :param ttl_minutes: 有效期(分钟), 用于文案提示
        :return: 是否发送成功
        """
        return await self._send(
            email,
            subject="验证码",
            body=f"您的验证码为 {code},{ttl_minutes} 分钟内有效。若非本人操作请忽略本邮件。",
        )


# 全局单例(无状态, 复用避免重复构造)
_email_service = EmailService()


def get_email_service() -> EmailService:
    """EmailService 依赖注入工厂(FastAPI Depends 使用)"""
    return _email_service
