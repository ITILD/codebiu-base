"""注册流程配置: 邮箱验证开关(验证码缓存策略与收发已外置至 module_contact)"""
from common.config.dynamic import get_settings
from common.config.dynamic.schemas import EmailSettings


async def email_verify_enabled() -> bool:
    """是否开启注册邮箱验证码(email.use_for_register; 配置中心变更即时生效)"""
    return (await get_settings(EmailSettings)).use_for_register
