"""系统主模块 子应用装配: 路由挂载与模块级初始化"""

import logging

from common.config.lifespan import register_init_hook

logger = logging.getLogger(__name__)


@register_init_hook
async def bootstrap_default_dicts():
    """幂等补齐注册中心声明的基础字典种子(sys 通用 + 各模块域,只补缺不覆盖)"""
    from module_main.config.dict_seed import ensure_default_dicts
    await ensure_default_dicts()
    logger.info("Default dicts bootstrap successfully.")


@register_init_hook
async def bootstrap_audit_log():
    """操作审计(REQ-009): 注册中间件落库 sink, 并按保留期清理过期记录"""
    from common.middleware.audit import audit_recorder
    from module_main.service.audit_log import audit_sink, purge_expired

    audit_recorder.set_sink(audit_sink)
    await purge_expired()
    logger.info("Audit log bootstrap successfully.")


logger.debug("ok...server module_main服务配置")
