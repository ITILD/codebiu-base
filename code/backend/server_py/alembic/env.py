"""Alembic 迁移环境: 复用主服务三级配置构建同步引擎(SQLite/PostgreSQL 双后端)

关键设计:
- 连接来源与主服务完全一致: config.yaml → 环境层(APP_ENV) → CODEBIU_* 环境变量(db_rel 节),
  换库只需改同一份配置, 迁移与服务永不分叉
- 同步驱动: sqlite=内置驱动, postgres=psycopg(v3, 已在依赖);
  刻意不用 asyncpg/aiosqlite, 使 CLI 迁移与 lifespan 内嵌 stamp 均可在事件循环内直接调用
- 模型注册: import app 触发全部模块 do 导入, 与主服务 create_all 共享同一份 SQLModel.metadata
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# src 加入导入路径(与 pytest pythonpath 约定一致; CLI 需在 server_py 目录执行)
sys.path.insert(0, "src")

# alembic.ini 日志配置
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入全部表模型(触发所有模块 do 注册到 SQLModel.metadata)
import app  # noqa: E402

from sqlmodel import SQLModel  # noqa: E402

target_metadata = SQLModel.metadata


def _resolve_url() -> str:
    """从主服务配置解析同步连接串(与各 impl 的异步 URL 一一对应)

    postgres 密码含特殊字符时需 URL 编码, 与 db_postgre 实现保持同一口径(暂不处理)。
    """
    from common.config.index import conf

    db = conf.db_rel
    if db.type == "sqlite":
        # 与 DBSqlite 实现一致: 相对路径基于 CWD 规范化为绝对路径
        return f"sqlite:///{Path(db.database).absolute()}"
    if db.type == "postgres":
        return (
            f"postgresql+psycopg://{db.user}:{db.password}"
            f"@{db.host}:{db.port}/{db.database}"
        )
    raise ValueError(f"不支持的关系库类型: {db.type}(迁移仅支持 sqlite/postgres)")


def run_migrations_offline() -> None:
    """离线模式: 仅按元数据生成 SQL 脚本, 不连接数据库"""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # SQLite 变更列需重建表, batch 模式保证生成可执行脚本
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式: 同步连接直接执行迁移"""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
