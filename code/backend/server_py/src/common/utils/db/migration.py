"""数据库迁移辅助(REQ-008): 首启自动 stamp 与版本查询

约定:
- 全新库首启走 create_all, 随后自动 `alembic stamp head` 打上基线标记
- 之后结构演进一律 `alembic revision --autogenerate` + `alembic upgrade head`(手动执行)
- 启动期只打标不升级: 避免多 worker 竞争与长事务拖慢启动
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect

logger = logging.getLogger(__name__)

# alembic 版本表名(框架默认)
VERSION_TABLE = "alembic_version"
# alembic.ini 位置(与 config.yaml 同级, 均要求在 server_py 目录下启动)
ALEMBIC_INI = Path("alembic.ini")


def _alembic_config():
    """构建 alembic Config(入口文件缺失即抛错, 由调用方兜底)"""
    from alembic.config import Config

    if not ALEMBIC_INI.exists():
        raise FileNotFoundError(f"未找到 {ALEMBIC_INI}(alembic 命令需在 server_py 目录执行)")
    return Config(str(ALEMBIC_INI))


async def stamp_if_fresh() -> bool:
    """全新库(无版本表)自动 stamp 到最新版本; 已有版本表则跳过

    Returns:
        是否执行了 stamp(False=已有版本表跳过 或 失败告警)
    """
    from alembic import command

    from common.config.db import manager

    try:
        mgr = manager()
        if mgr.db_rel is None or mgr.db_rel.engine is None:
            logger.warning("alembic stamp 跳过: 关系库未启用/未连接")
            return False
        # 先探测版本表: 已运维库可能手工维护版本, 不得覆盖
        async with mgr.db_rel.engine.connect() as conn:
            has_version = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).has_table(VERSION_TABLE)
            )
        if has_version:
            return False
        command.stamp(_alembic_config(), "head")
        logger.info("alembic: 全新库已自动 stamp 到 head")
        return True
    except Exception as e:
        # 打标失败不阻断启动(可手动 `alembic stamp head` 补救)
        logger.warning(f"alembic stamp 失败(不影响启动, 可手动补打): {e}")
        return False
