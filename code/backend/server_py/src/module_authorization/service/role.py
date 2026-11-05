"""权限认证模块 role 业务逻辑层"""

import logging

from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from common.utils.fastapi_ex.exceptions import ConflictError, NotFoundError
from module_authorization.do.role import Role, RoleCreate, RoleUpdate, RoleResponse, RoleBatchDelete
from module_authorization.dao.role import RoleDao

logger = logging.getLogger(__name__)


class RoleService:
    """角色服务"""

    def __init__(self, role_dao: RoleDao):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.role_dao = role_dao or RoleDao()

    async def add(self, role: RoleCreate):
        """
        创建角色
        :param role: 角色创建数据
        :return: 创建的角色ID
        """
        return await self.role_dao.add(role)

    async def delete(self, role_id: str):
        """
        删除角色(同时清理该角色的权限策略与用户分配关系)
        :param role_id: 角色ID
        """
        role = await self.role_dao.get(role_id)
        if not role:
            raise NotFoundError(f"未找到ID为 {role_id} 的角色")
        await self.role_dao.delete(role_id)
        await self._purge_role_relations([role.role_key])

    async def batch_delete(self, batch_delete: RoleBatchDelete) -> int:
        """
        批量删除角色(不存在的ID静默跳过, 同时清理 Casbin 关联策略)
        :param batch_delete: 批量删除请求(含角色ID列表)
        :return: 实际删除数量
        """
        roles = await self.role_dao.list_by_ids(batch_delete.ids)
        deleted_count = await self.role_dao.batch_delete(batch_delete.ids)
        await self._purge_role_relations([role.role_key for role in roles])
        return deleted_count

    async def _purge_role_relations(self, role_keys: list[str]) -> None:
        """
        清理角色关联的 Casbin 策略(角色权限 + 用户角色分配)。
        清理失败仅记录日志, 不影响已完成的角色删除。
        :param role_keys: 角色权限字符串列表
        """
        if not role_keys:
            return
        try:
            from module_authorization.service.casbin_rule import CasbinRuleService
            casbin_service = CasbinRuleService()
            for role_key in role_keys:
                await casbin_service.delete_role_permissions(role_key)
                await casbin_service.delete_role_groupings(role_key)
        except Exception as e:
            logger.warning(f"清理角色策略失败: {e}")

    async def update(self, role_id: str, role: RoleUpdate):
        """
        更新角色(名称/权限字符被修改时校验唯一性)
        :param role_id: 角色ID
        :param role: 角色更新数据
        """
        if role.name:
            existing = await self.role_dao.get_by_name(role.name)
            if existing and existing.id != role_id:
                raise ConflictError(f"角色名称 '{role.name}' 已存在")
        if role.role_key:
            existing = await self.role_dao.get_by_role_key(role.role_key)
            if existing and existing.id != role_id:
                raise ConflictError(f"角色权限字符 '{role.role_key}' 已存在")
        await self.role_dao.update(role_id, role)

    async def get(self, role_id: str) -> Role | None:
        """
        获取角色详情
        :param role_id: 角色ID
        :return: 角色对象
        """
        return await self.role_dao.get(role_id)

    async def get_by_name(self, name: str) -> Role | None:
        """根据角色名称获取角色"""
        return await self.role_dao.get_by_name(name)

    async def get_by_role_key(self, role_key: str) -> Role | None:
        """根据角色权限字符串获取角色"""
        return await self.role_dao.get_by_role_key(role_key)

    async def list_all(self) -> list[Role]:
        """获取所有角色(不分页)"""
        return await self.role_dao.list_all()

    async def list_paged(
        self,
        pagination: PaginationParams,
        name: str | None = None,
        role_key: str | None = None,
        is_active: bool | None = None,
    ) -> PaginationResponse:
        """
        分页获取角色列表(支持多字段过滤)
        :param pagination: 分页参数
        :param name: 角色名称模糊匹配
        :param role_key: 权限字符模糊匹配
        :param is_active: 状态精确过滤(启用/禁用)
        """
        items = await self.role_dao.list_paged(
            pagination, name=name, role_key=role_key, is_active=is_active
        )
        total = await self.role_dao.count(
            name=name, role_key=role_key, is_active=is_active
        )
        return PaginationResponse.create(items, total, pagination)