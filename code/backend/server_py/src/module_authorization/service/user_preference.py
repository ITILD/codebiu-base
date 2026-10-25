"""权限认证模块 user_preference 业务逻辑层"""

from module_authorization.dao.user_preference import UserPreferenceDao
from module_authorization.do.user_preference import (
    THEME_MODES,
    UserPreferenceResponse,
    UserPreferenceUpdate,
)


class UserPreferenceService:
    """用户样式偏好服务(当前用户自助读写)"""

    def __init__(self, preference_dao: UserPreferenceDao):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.preference_dao = preference_dao or UserPreferenceDao()

    async def get(self, user_id: str) -> UserPreferenceResponse:
        """
        获取用户样式偏好
        :param user_id: 用户ID
        :return: 偏好记录(未设置时返回系统默认 auto)
        """
        preference = await self.preference_dao.get_by_user_id(user_id)
        return preference or UserPreferenceResponse()

    async def save(
        self, user_id: str, preference: UserPreferenceUpdate
    ) -> UserPreferenceResponse:
        """
        保存用户样式偏好(新增或更新)
        :param user_id: 用户ID
        :param preference: 偏好数据
        :return: 保存后的偏好记录
        :raises: ValueError 主题模式不在允许范围内(由全局处理器映射为 400)
        """
        if preference.theme not in THEME_MODES:
            raise ValueError(f"不支持的主题模式: {preference.theme}")
        return await self.preference_dao.upsert(user_id, preference.theme)
