"""系统主模块 操作审计日志 FastAPI 依赖注入"""

from fastapi import Depends

from module_main.dao.audit_log import AuditLogDao
from module_main.service.audit_log import AuditLogService


async def get_audit_log_dao() -> AuditLogDao:
    """审计日志DAO工厂"""
    return AuditLogDao()


async def get_audit_log_service(
    dao: AuditLogDao = Depends(get_audit_log_dao),
) -> AuditLogService:
    """审计日志Service工厂"""
    return AuditLogService(dao)
