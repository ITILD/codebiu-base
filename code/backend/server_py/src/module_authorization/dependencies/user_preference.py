"""权限认证模块 user_preference FastAPI 依赖注入"""

from fastapi import Depends

from module_authorization.dao.user_preference import UserPreferenceDao
from module_authorization.service.user_preference import UserPreferenceService


async def get_user_preference_dao():
    """DAO工厂"""
    return UserPreferenceDao()


async def get_user_preference_service(
    dao: UserPreferenceDao = Depends(get_user_preference_dao),
):
    """Service工厂"""
    return UserPreferenceService(dao)
