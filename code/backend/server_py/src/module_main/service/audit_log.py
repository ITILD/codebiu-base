"""系统主模块 操作审计日志服务(REQ-009): 查询/过期清理/中间件落库入口"""

import logging
from datetime import datetime
from typing import Any

from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_main.dao.audit_log import AuditLogDao
from module_main.do.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditLogService:
    def __init__(self, dao: AuditLogDao):
        self.dao = dao

    async def list_paged(
        self,
        pagination: PaginationParams,
        user_id: str | None = None,
        username: str | None = None,
        method: str | None = None,
        keyword: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> PaginationResponse:
        """条件过滤分页查询审计日志"""
        items, total = await self.dao.query_paged(
            pagination,
            user_id=user_id,
            username=username,
            method=method,
            keyword=keyword,
            start=start,
            end=end,
        )
        return PaginationResponse.create(items, total, pagination)


async def audit_sink(entries: list[dict[str, Any]]) -> None:
    """中间件落库入口: 缓冲条目(dict) → 表模型批量写入(注册为 audit_recorder 的 sink)"""
    logs = [AuditLog.model_validate(e) for e in entries]
    await AuditLogDao().add_many(logs)


async def purge_expired() -> int:
    """按动态配置保留期清理过期审计记录(启动钩子触发; 周期清理由 REQ-012 定时任务接入)"""
    from common.config.dynamic import get_settings
    from common.config.dynamic.schemas import AuditSettings

    settings = await get_settings(AuditSettings)
    deleted = await AuditLogDao().purge_expired(settings.retention_days)
    if deleted:
        logger.info(f"操作审计: 已清理超过 {settings.retention_days} 天的记录 {deleted} 条")
    return deleted
