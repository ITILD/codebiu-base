"""
langgraph AsyncPostgresSaver checkpointer 配置(模块级单例)

- 使用 psycopg AsyncConnectionPool 连接 PostgreSQL
- 连接池配置 autocommit=True(setup 的 CREATE INDEX CONCURRENTLY 需要在事务块外运行)
- setup() 创建 checkpointer 所需的表和索引
- 通过 asyncio.Lock 防止并发初始化竞态
"""
# 注解延迟求值: 允许类型注解引用延迟导入的 langgraph/psycopg_pool
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from common.config.index import conf

if TYPE_CHECKING:
    # langgraph(+psycopg_pool) 重量级依赖延迟到 get_checkpointer() 首次调用时导入
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_init_lock = asyncio.Lock()


def _build_pg_conn_string() -> str:
    """从配置构建 postgres 连接字符串(psycopg 格式，不含 +asyncpg)"""
    db = conf.db_rel
    return f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.database}"


async def _configure_conn(conn) -> None:
    """连接池配置回调：设置 autocommit

    setup() 内的 CREATE INDEX CONCURRENTLY 要求在事务块外运行，
    因此每个连接创建后立即开启 autocommit。

    注意：异步连接的 autocommit 属性只读，必须使用 set_autocommit()。
    """
    await conn.set_autocommit(True)


async def get_checkpointer() -> AsyncPostgresSaver:
    """
    获取 AsyncPostgresSaver 单例

    首次调用时：
    1. 创建 AsyncConnectionPool(configure=_configure_conn, open=False)
    2. 打开连接池
    3. 创建 AsyncPostgresSaver 并执行 setup() 建表

    后续调用直接返回已创建的实例。
    通过 asyncio.Lock 防止并发请求重复初始化。
    """
    global _pool, _checkpointer

    # 重量级依赖延迟导入(langgraph 连带加载约 50MB+)
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from psycopg_pool import AsyncConnectionPool

    # checkpoint 业务类型白名单: state 中以对象形式持久化的自定义模型必须在此登记,
    # 否则升级 langgraph(将默认拒绝未注册类型)后旧会话恢复会直接失败
    # (SAFE_MSGPACK_TYPES 内置类型与 langchain 消息类型自动放行, 无需重复登记)
    from module_rag.do.project_document_chunk import ProjectDocumentChunkSearchResponse
    from module_rag.do.rag_chat import ConversationSummary, RagHelpInfo, WebCitation

    rag_state_types = (
        RagHelpInfo,
        WebCitation,
        ConversationSummary,
        ProjectDocumentChunkSearchResponse,
    )

    if _checkpointer is not None:
        return _checkpointer

    async with _init_lock:
        # 防止其他协程初始化
        if _checkpointer is not None:
            return _checkpointer

        conn_string = _build_pg_conn_string()
        logger.info("正在初始化 AsyncPostgresSaver checkpointer...")

        # configure 作为构造参数传入，确保连接创建时即开启 autocommit
        pool = AsyncConnectionPool(
            conninfo=conn_string,
            open=False,
            configure=_configure_conn,
        )
        try:
            await pool.open()
            # 显式注册业务类型白名单: 消除"unregistered type"反序列化告警,
            # 并在 langgraph 收紧默认策略后仍可恢复存量会话
            saver = AsyncPostgresSaver(
                pool, serde=JsonPlusSerializer(allowed_msgpack_modules=rag_state_types)
            )
            await saver.setup()
        except BaseException as e:
            await pool.close()   # 失败时回收
            raise e

        _pool = pool             # 全部成功后才写入全局
        _checkpointer = saver
        logger.info("AsyncPostgresSaver checkpointer 初始化完成")
        return _checkpointer


async def close_checkpointer() -> None:
    """关闭 checkpointer 和连接池(应用关闭时调用)"""
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
        _pool = None
        _checkpointer = None
        logger.info("AsyncPostgresSaver checkpointer 已关闭")
