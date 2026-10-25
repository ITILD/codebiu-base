"""权限认证模块 user_preference 数据访问层"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from module_authorization.do.user_preference import UserPreference, UserPreferenceResponse


class UserPreferenceDao:
    """用户样式偏好数据访问对象"""

    @DaoRel
    async def get_by_user_id(
        self, user_id: str, session: AsyncSession | None = None
    ) -> UserPreferenceResponse | None:
        """
        按用户ID查询样式偏好
        :param user_id: 用户ID
        :param session: 可选数据库会话
        :return: 偏好记录, 未设置返回 None
        """
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.exec(stmt)
        preference = result.first()
        if not preference:
            return None
        return UserPreferenceResponse.model_validate(preference.model_dump())

    @DaoRel
    async def upsert(
        self, user_id: str, theme: str, session: AsyncSession | None = None
    ) -> UserPreferenceResponse:
        """
        写入用户样式偏好(不存在则新增, 存在则更新主题)
        :param user_id: 用户ID
        :param theme: 主题模式
        :param session: 可选数据库会话
        :return: 保存后的偏好记录
        """
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await session.exec(stmt)
        preference = result.first()
        if preference:
            preference.theme = theme
        else:
            preference = UserPreference(user_id=user_id, theme=theme)
            session.add(preference)
        await session.flush()
        return UserPreferenceResponse.model_validate(preference.model_dump())
