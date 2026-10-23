"""系统主模块 操作审计日志数据访问层(REQ-009)"""

from datetime import datetime, timedelta, timezone

from sqlmodel import col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from common.utils.db.schema.pagination import PaginationParams
from module_main.do.audit_log import AuditLog


class AuditLogDao:
    @DaoRel
    async def add_many(self, logs: list[AuditLog], session: AsyncSession | None = None) -> int:
        """批量写入审计记录(中间件缓冲攒批, 单事务落库)"""
        session.add_all(logs)
        await session.flush()
        return len(logs)

    @DaoRel
    async def query_paged(
        self,
        pagination: PaginationParams,
        user_id: str | None = None,
        username: str | None = None,
        method: str | None = None,
        keyword: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[list[AuditLog], int]:
        """条件过滤分页查询(按记录时间倒序), 返回 (当前页记录, 总数)"""
        conditions = []
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if username:
            conditions.append(col(AuditLog.username).contains(username))
        if method:
            conditions.append(AuditLog.method == method.upper())
        if keyword:
            conditions.append(col(AuditLog.path).contains(keyword))
        if start:
            conditions.append(AuditLog.created_at >= start)
        if end:
            conditions.append(AuditLog.created_at <= end)

        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)
        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await session.exec(count_stmt)).one()
        stmt = (
            stmt.order_by(col(AuditLog.created_at).desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        items = (await session.exec(stmt)).all()
        return items, total

    @DaoRel
    async def purge_expired(self, retention_days: int, session: AsyncSession | None = None) -> int:
        """删除超过保留期的审计记录, 返回删除条数"""
        threshold = datetime.now(timezone.utc) - timedelta(days=retention_days)
        stmt = delete(AuditLog).where(AuditLog.created_at < threshold)
        result = await session.exec(stmt)
        await session.flush()
        return result.rowcount
