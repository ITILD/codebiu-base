"""应用生命周期: 启动时装配连接/自动建表/种子数据/权限初始化"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.config.index import conf
from common.config.db import db_manager
import logging

logger = logging.getLogger(__name__)

# 模块钩子表:各模块在 config/server.py 导入期用装饰器注册,
# 未被 app.py 加载的模块不会注册,天然随模块启停
STARTUP_HOOKS = []  # 建表前执行(如启用 PostGIS 扩展)
INIT_HOOKS = []     # 建表后执行(如 casbin 策略/种子数据初始化)


def register_startup_hook(hook):
    """注册建表前钩子(可作装饰器使用,失败仅告警)"""
    STARTUP_HOOKS.append(hook)
    return hook


def register_init_hook(hook):
    """注册建表后钩子(可作装饰器使用,失败仅告警)"""
    INIT_HOOKS.append(hook)
    return hook


async def run_hooks(hooks):
    """依序执行钩子,单个失败仅告警不阻断启动"""
    for hook in hooks:
        try:
            await hook()
        except Exception as e:
            logger.warning(f"startup hook failed [{hook.__name__}]: {e}")


async def server_start():
    """服务启动流程: 装配runtime→(check_db)建表前钩子→建表→建表后钩子

    state.check_db(config.yaml, 默认 true)=启动自检开关:
    true 时自动建表 + 首启种子(全新项目保持 true); false 时跳过建表与初始化钩子
    (适用于库结构已就绪、不希望启动触碰数据的场景)。
    """
    logger.info("server_start...")
    # 显式装配运行时(db_rel 引导→sys_config表→种子→任务快照→其余数据库),
    # 连接从 import 期移入装配点, 治理 import 期副作用
    from common.runtime import init_runtime

    await init_runtime()
    # 启动自检开关(默认 true): false = 库已就绪, 跳过建表与数据初始化
    check_db: bool = bool(conf.get("state.check_db", True))
    try:
        await db_manager.connect_all()
        if not check_db:
            logger.info("state.check_db=false, 跳过建表与初始化钩子(库结构需已就绪)")
            return
        # 建表前钩子(如启用数据库扩展,必须先于建表)
        await run_hooks(STARTUP_HOOKS)
        await db_manager.table_create_all()
        logger.info("Database tables init successfully.")
    except Exception as e:
        logger.error(f"server_start error: {e}")
        check_db = False

    # 建表后钩子(casbin 策略/默认管理员/字典种子等,即使建表失败也照常尝试)
    if check_db:
        await run_hooks(INIT_HOOKS)

    


async def server_end():
    """服务关闭流程:释放数据库等资源"""
    logger.info("server_end...")
    # redis持久化 英文
    await db_manager.shutdown()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理:启动时初始化数据库,关闭时释放资源"""
    # 启动时执行
    await server_start()

    # 启动地址
    logger.info("%s%s", "server:http://127.0.0.1:", conf.server.port)
    logger.info("%s%s%s", "docs:http://127.0.0.1:", conf.server.port, "/docs")
    
    yield
    # 关闭时执行
    await server_end()
