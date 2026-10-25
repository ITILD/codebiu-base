"""系统主模块 多语言词条覆盖 FastAPI 依赖注入"""

from fastapi import Depends

from module_main.dao.i18n import I18nDao
from module_main.service.i18n import I18nService


async def get_i18n_dao() -> I18nDao:
    """词条覆盖DAO工厂"""
    return I18nDao()


async def get_i18n_service(dao: I18nDao = Depends(get_i18n_dao)) -> I18nService:
    """词条覆盖Service工厂"""
    return I18nService(dao)
