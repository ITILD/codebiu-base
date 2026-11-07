"""
Celery 任务队列入口(Worker 启动文件 / 消费进程)

用法:
    python src/app_task.py         # 启动单个 worker(消费 task_queue 队列)
    celery -A src.app_task worker  # 等价命令行方式(Windows 建议加 --pool=solo)
    celery -A src.app_task beat    # 周期调度触发进程(需要定时任务时启动, 单实例;
                                   # 每分钟 tick 一次, 调度定义在 任务管理→定时任务 热更)

多实例横向扩容:
    同机多开直接重复执行 `python src/app_task.py` 即可 —— 节点名自动携带 PID
    (task_worker@<主机名>#<PID>), 互不冲突; 所有实例竞争消费同一 task_queue 队列,
    由 Redis 分级子队列按任务 priority(0~9, 越大越优先)加权派发。

说明:
    - 所有后台任务(文档解析/重向量化/审计清理等)统一经本 worker 进程执行,
      复杂解析等重活不占用 API 进程(API 只负责创建任务与查询进度)
    - broker/backend 由 config.yaml 的 tasks 段或 系统管理→通用配置 提供
      (未配置时默认 memory://, 消息不出进程, 适合开发/测试)
    - worker 消费 task_queue 队列, 任务执行中把 状态/百分比/阶段消息 实时回写 PostgreSQL
    - API 服务(app.py)与 worker(app_task.py) 可独立部署重启, 互不影响
    - 任务函数是"薄启动器": 经 load_task 读取 payload 与创建者 user_id,
      调用业务模块自己的 service 执行
    - 任务账户与权限: worker 启动时以只读方式初始化 casbin enforcer,
      任务执行时以创建者 user_id 实时复检资源权限(权限回收后任务安全失败)

启动流程:
    建表(幂等) → 初始化权限上下文(只读) → 启动 Reaper 自愈线程 → 启动消费循环

Reaper 自愈线程(多实例安全):
    每 60s 执行一轮自愈(重派发遗留 PENDING + 清扫僵尸 RUNNING); 多实例部署时
    经 Redis 分布式锁(SET NX EX)竞争上岗, 同一时刻仅一个实例执行扫描 ——
    所有实例统一启动即可, 无需区分谁开谁关, 持锁实例宕机后锁自动过期,
    其他实例下个周期自动接管(故障转移)。详见 _reaper_process 注释。
"""
import logging
import os
import socket
import threading
import time

from common.config.tasks import app as celery_app

# 导入任务注册(Worker 进程必须导入任务模块, 否则对应任务无法被路由执行)
from module_task.tasks import demo, maintenance, schedule_beat  # noqa: F401
from module_rag.tasks import project_document, project_document_chunk  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = ("celery_app",)

# Reaper 自愈线程参数
_REAPER_INTERVAL = 60  # 扫描周期(秒)
_REAPER_WARMUP = 10    # 启动预热: 等消费循环与连接池就绪后再开始扫描
_REAPER_LOCK_KEY = "sys:task:reaper:lock"
_lock_redis = None     # 锁专用 Redis 连接(惰性创建, 复用 broker 连接信息)


def _get_lock_redis():
    """
    获取锁专用 Redis 连接(复用 broker 连接信息)
    :return: redis 客户端; 非 Redis broker(memory://)返回 None → 单进程语义, 无需锁
    """
    global _lock_redis
    from common.config.tasks import BROKER_URL

    if not BROKER_URL.startswith("redis"):
        return None
    if _lock_redis is None:
        import redis

        _lock_redis = redis.Redis.from_url(BROKER_URL, socket_timeout=3)
    return _lock_redis


async def _ensure_task_table() -> None:
    """Worker 进程内幂等建表与连接(常规由 API 启动时创建, worker 侧自愈补齐)"""
    from common.runtime import init_runtime

    # Worker 装配点: db_rel 引导→sys_config表→种子→任务快照→其余数据库连接
    await init_runtime()

    from common.config.db import db_manager

    # 向量库连接 + 全量建表(均幂等; RAG 文档解析任务写向量表依赖)
    await db_manager.connect_all()
    await db_manager.table_create_all()
    logger.info("task tables and vector db ensured.")


def _reaper_process() -> None:
    """
    常驻自愈线程(Reaper): 周期执行 recover_pending_tasks + fail_stale_running_tasks

    分布式锁设计(多实例竞争上岗, 全局单例执行):
    - 抢锁: SET NX EX —— 锁不存在才设置(nx), 并带过期时间(ex)
    - 锁 TTL < 扫描周期: 持锁实例宕机来不及释放, 锁自动过期后
      其他实例下个周期能正常抢到, 自动接管(故障转移);
      若 TTL >= 周期, 宕机后其余实例将连续拿不到锁, 自愈漏执行
    - 锁 TTL > 单轮扫描耗时: 防止扫描期间锁过期导致两实例同时执行
      (任务扫描通常毫秒级, interval-15 的 TTL 余量充足)
    - 扫描完主动释放: 各实例轮流上岗, 均摊负载; 释放失败由 TTL 兜底
    - 非 Redis broker(memory://): 消息本就不出进程, 单实例语义, 无锁直跑
    - Redis 异常: 跳过本轮(宁可漏扫一轮, 不可无锁并发扫)
    """
    from module_task.tasks import (
        fail_stale_running_tasks,
        recover_pending_tasks,
        run_async,
    )

    lock_ttl = max(10, _REAPER_INTERVAL - 15)
    time.sleep(_REAPER_WARMUP)
    logger.info(
        f"Reaper 自愈线程已启动(周期 {_REAPER_INTERVAL}s, 锁 TTL {lock_ttl}s, key={_REAPER_LOCK_KEY})"
    )
    while True:
        redis_client = _get_lock_redis()
        acquired = True
        if redis_client is not None:
            try:
                acquired = bool(
                    redis_client.set(_REAPER_LOCK_KEY, "1", nx=True, ex=lock_ttl)
                )
            except Exception as exc:
                logger.warning(f"Reaper 抢锁失败(Redis 异常, 跳过本轮): {exc}")
                acquired = False
        if acquired:
            try:
                recovered = run_async(recover_pending_tasks())
                swept = run_async(fail_stale_running_tasks())
                if recovered or swept:
                    logger.info(f"Reaper 自愈完成: 重派发 {recovered}, 清扫僵尸 {swept}")
            except Exception as exc:
                logger.warning(f"Reaper 自愈执行失败: {exc}")
            finally:
                if redis_client is not None:
                    try:
                        redis_client.delete(_REAPER_LOCK_KEY)
                    except Exception:
                        pass  # 释放失败由 TTL 兜底
        else:
            logger.debug("Reaper 未获取到锁, 其他实例正在执行, 跳过本轮扫描")
        time.sleep(_REAPER_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 通过 worker 常驻循环执行(与任务协程共享同一连接池所在的事件循环)
    from module_task.tasks import (
        init_worker_authorization,
        run_async,
    )

    run_async(_ensure_task_table())
    # 权限上下文: 只读构建 casbin enforcer(任务执行时以创建者身份复检权限)
    run_async(init_worker_authorization())
    # 常驻自愈线程: 分布式锁竞争上岗(多实例安全), 周期重派发 PENDING + 清扫僵尸 RUNNING
    threading.Thread(target=_reaper_process, daemon=True, name="task-reaper").start()

    # Windows 推荐 solo 池(单进程顺序消费); 生产环境可换 prefork/gevent 并调大 concurrency
    # 节点名携带 PID: 同机多开多个 worker 实例互不冲突, 竞争消费同一队列
    node_name = f"task_worker@{socket.gethostname()}#{os.getpid()}"
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=info",
            "--pool=solo",
            "--concurrency=1",
            "--queues=task_queue",
            f"--hostname={node_name}",
        ]
    )
