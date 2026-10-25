"""系统主模块 代码生成器 FastAPI 依赖注入"""

from fastapi import Depends

from module_main.dao.codegen import CodegenDao
from module_main.service.codegen import CodegenService


async def get_codegen_dao() -> CodegenDao:
    """代码生成器DAO工厂"""
    return CodegenDao()


async def get_codegen_service(
    dao: CodegenDao = Depends(get_codegen_dao),
) -> CodegenService:
    """代码生成器Service工厂"""
    return CodegenService(dao)
