"""
Celery 任务队列入口(Worker 启动文件 / 消费进程)

用法:
    python src/app_task.py                       # 启动 worker(默认 solo 池, 消费 task_queue,q_interactive)
    TASK_POOL=prefork TASK_CONCURRENCY=4 python src/app_task.py   # 生产多进程 worker
    TASK_ROLE=beat python src/app_task.py        # 周期调度触发进程(全局单实例)

环境变量(argparse 与 env 双通道, env 为 compose 部署主通道):
    TASK_QUEUES(兼容 WORKER_QUEUES)  监听队列(逗号分隔, 默认 task_queue,q_interactive)
    TASK_POOL                         执行池 solo/prefork/threads, 默认 solo
    TASK_CONCURRENCY                  并发数, 默认 1
    TASK_WORKER_NAME                  节点名(默认 task_worker@<主机名>#<PID>)
    TASK_LOG_LEVEL                    日志级别, 默认 info
    TASK_REAPER                       自愈开关(1/0), 默认 1
    TASK_MAX_TASKS_PER_CHILD          仅 prefork: 子进程处理 N 个任务后重启(防内存泄漏累积), 0=关
    TASK_ROLE                         worker / beat, 默认 worker

说明:
    - 同一镜像/同一入口可参数化启动为不同角色/池型/队列的执行器
    - 所有后台任务(文档解析/重向量化/审计清理等)统一经 worker 进程执行,
      复杂解析等重活不占用 API 进程(API 只负责创建任务与查询进度)
    - broker/backend 由 config.yaml 的 tasks 段或 系统管理→通用配置 提供
      (未配置时默认 memory://, 消息不出进程, 适合开发/测试)
    - 任务函数是"薄启动器": 经 load_task 读取 payload 与创建者 user_id,
      调用业务模块自己的 service 执行; 执行中以创建者 user_id 实时复检资源权限

池型说明:
    - solo:     单进程顺序消费(Windows 推荐); Reaper 用线程; 启动时进程内完成建表/权限初始化
    - prefork:  多进程池(生产推荐); 父进程不触达 DB, Reaper 用独立子进程(fork 前父进程干净),
                每个子进程首次执行任务时惰性初始化(连接池/建表/权限, 见 module_task.tasks)
    - threads:  线程池; 行为同 solo(进程内初始化, Reaper 用线程)

可靠性配置(由 common/config/tasks.py 统一提供, 此处仅启动参数):
    prefetch_multiplier=1(公平抢占不囤积) + acks_late + reject_on_worker_lost
    => worker 进程被 kill 后消息由 broker 秒级重投, 配合 Reaper 兜底对账

启动流程(worker):
    Reaper 自愈(池型决定线程/进程) → 心跳注册线程 → 启动消费循环
    (进程内初始化按池型: solo/threads 显式预热, prefork 由子任务惰性触发)

心跳注册线程(执行器 IP/状态可视化的数据源):
    每 30s 写 broker Redis sys:task:worker:hb:<节点名> =
    {name, hostname, ip, pid, queues, pool, concurrency, started_at, last_seen},
    EX 90s(进程死亡后 90s 内键过期, 主服务面板据此展示 offline 与最近心跳);
    非 Redis broker(memory://)自动禁用。
"""
import logging
import multiprocessing
import os
import socket
import threading
import time

from common.config.tasks import app as celery_app

# 导入任务注册(Worker 进程必须导入任务模块, 否则对应任务无法被路由执行)
from module_task.tasks import demo, maintenance, schedule_beat  # noqa: F401
from module_rag.tasks import project_document, project_document_chunk  # noqa: F401
from module_agent import tasks as agent_tasks  # noqa: F401 (REQ-018: skill_execute / agent_job_execute)
# worker 侧动态队列订阅(worker_ready 对齐注册表 + 周期对账; 仅 worker 角色生效)
from module_task.tasks import subscription  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = ("celery_app",)

# Reaper 自愈参数
_REAPER_INTERVAL = 60  # 扫描周期(秒)
_REAPER_WARMUP = 10    # 启动预热: 等消费循环与连接池就绪后再开始扫描
_REAPER_LOCK_KEY = "sys:task:reaper:lock"
_lock_redis = None     # 锁/心跳专用 Redis 连接(惰性创建, 复用 broker 连接信息)

# 心跳注册参数
_HB_INTERVAL = 30        # 心跳周期(秒)
_HB_TTL = 90             # 心跳键过期时间(秒): 进程死亡后 90s 内自然消失
_HB_KEY_PREFIX = "sys:task:worker:hb:"


def _get_lock_redis():
    """
    获取锁/心跳专用 Redis 连接(复用 broker 连接信息)
    :return: redis 客户端; 非 Redis broker(memory://)返回 None → 单进程语义, 无需锁/心跳
    """
    global _lock_redis
    from common.config.tasks import BROKER_URL

    if not BROKER_URL.startswith("redis"):
        return None
    if _lock_redis is None:
        import redis

        _lock_redis = redis.Redis.from_url(BROKER_URL, socket_timeout=3)
    return _lock_redis


def _detect_ip() -> str:
    """
    探测本机出口 IP(心跳注册展示用)
    优先 UDP 连 broker host 取出口地址(不实际发包), 失败回落解析本机主机名
    """
    from urllib.parse import urlparse

    try:
        from common.config.tasks import BROKER_URL

        parsed = urlparse(BROKER_URL)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6379
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.connect((host, port))
            return s.getsockname()[0]
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "unknown"


def _heartbeat_thread(node_name: str, queues: list[str], pool: str,
                      concurrency: int, started_at: float) -> None:
    """
    心跳注册线程: 周期写 broker Redis 的执行器心跳键(带 TTL)

    主服务 workers() 接口经 SCAN+GET 合并心跳与 inspect 结果, 提供
    IP/hostname/运行时长/离线状态; 键过期即判定实例已死(90s 内)。
    Redis 异常仅跳过本轮, 不影响 worker 消费。
    """
    import json

    redis_client = _get_lock_redis()
    if redis_client is None:
        logger.debug("非 Redis broker, 心跳注册已禁用")
        return
    key = f"{_HB_KEY_PREFIX}{node_name}"
    hostname = socket.gethostname()
    ip = _detect_ip()
    logger.info(f"心跳注册线程已启动(周期 {_HB_INTERVAL}s, key={key}, ip={ip})")
    while True:
        payload = {
            "name": node_name,
            "hostname": hostname,
            "ip": ip,
            "pid": os.getpid(),
            "queues": queues,
            "pool": pool,
            "concurrency": concurrency,
            "started_at": started_at,
            "last_seen": time.time(),
        }
        try:
            redis_client.set(key, json.dumps(payload), ex=_HB_TTL)
        except Exception as exc:
            logger.debug(f"心跳写入失败(下轮重试): {exc}")
        time.sleep(_HB_INTERVAL)


def _reaper_loop() -> None:
    """
    常驻自愈循环(Reaper): 周期执行 recover_pending_tasks + fail_stale_running_tasks

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
        f"Reaper 自愈循环已启动(周期 {_REAPER_INTERVAL}s, 锁 TTL {lock_ttl}s, key={_REAPER_LOCK_KEY})"
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


def _split_env(value: str | None) -> list[str]:
    """逗号分隔字符串 -> 去空列表"""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_flag(name: str, default: str = "1") -> bool:
    """读取布尔型环境变量(1/true/yes 为真)"""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def main() -> None:
    """
    构造 worker/beat 启动参数并运行(角色由 TASK_ROLE 决定)
    """
    logging.basicConfig(
        level=getattr(logging, os.environ.get("TASK_LOG_LEVEL", "info").upper(), logging.INFO)
    )
    # ---- 角色分支: beat(周期调度触发, 全局单实例, 无 Reaper/心跳) ----
    if os.environ.get("TASK_ROLE", "worker").strip().lower() == "beat":
        logger.info("以 beat 角色启动(每分钟 tick, 调度定义落库热更; 全局单实例)")
        celery_app.start(argv=["beat", "--loglevel", "INFO"])
        return

    # ---- worker 角色: 解析参数(env 为主, 兼容 WORKER_QUEUES) ----
    queues = _split_env(
        os.environ.get("TASK_QUEUES") or os.environ.get("WORKER_QUEUES")
    ) or ["task_queue", "q_interactive"]
    pool = os.environ.get("TASK_POOL", "solo").strip().lower()
    concurrency = max(1, int(os.environ.get("TASK_CONCURRENCY", "1")))
    node_name = (
        os.environ.get("TASK_WORKER_NAME", "").strip()
        or f"task_worker@{socket.gethostname()}#{os.getpid()}"
    )
    max_tasks_per_child = int(os.environ.get("TASK_MAX_TASKS_PER_CHILD", "0"))
    reaper_enabled = _env_flag("TASK_REAPER")
    # 显式指定队列(TASK_QUEUES/WORKER_QUEUES 任一) = 固定订阅, 不参与注册表动态对账;
    # 未指定 = 跟随队列注册表全量对账(增减队列秒级生效, 见 module_task.tasks.subscription)
    explicit_queues = bool(
        os.environ.get("TASK_QUEUES") or os.environ.get("WORKER_QUEUES")
    )

    started_at = time.time()
    logger.info(
        f"worker 启动: queues={queues} pool={pool} concurrency={concurrency} "
        f"name={node_name} explicit_queues={explicit_queues} "
        f"max_tasks_per_child={max_tasks_per_child}"
    )

    # ---- Reaper 自愈: solo/threads 用线程(进程内初始化安全), prefork 用独立子进程
    #    (fork 前父进程不触达 DB, 子进程各自经 run_async 惰性初始化) ----
    if reaper_enabled:
        if pool == "prefork":
            process = multiprocessing.Process(
                target=_reaper_loop, name="task-reaper", daemon=True
            )
            process.start()
            logger.info(f"Reaper 自愈子进程已启动: pid={process.pid}")
        else:
            threading.Thread(
                target=_reaper_loop, daemon=True, name="task-reaper"
            ).start()

    # ---- 进程内初始化(仅 solo/threads): prefork 父进程保持干净, 由子进程惰性初始化 ----
    from module_task.tasks import run_async

    if pool != "prefork":
        from module_task.tasks import ensure_worker_runtime

        run_async(ensure_worker_runtime())

    # ---- 心跳注册线程(所有池型都在主进程注册, 节点身份=主进程) ----
    threading.Thread(
        target=_heartbeat_thread,
        args=(node_name, queues, pool, concurrency, started_at),
        daemon=True,
        name="task-heartbeat",
    ).start()

    # ---- 消费循环 ----
    worker_argv = [
        "worker",
        f"--loglevel={os.environ.get('TASK_LOG_LEVEL', 'info')}",
        f"--pool={pool}",
        f"--concurrency={concurrency}",
        f"--queues={','.join(queues)}",
        f"--hostname={node_name}",
        # 每次只取 1 条任务: 多实例公平抢占, 不囤积(配合 acks_late 崩溃重投)
        "--prefetch-multiplier=1",
    ]
    # 仅 prefork: 子进程处理 N 个任务后重启, 防解析/OCR 内存泄漏累积(0=关闭)
    if pool == "prefork" and max_tasks_per_child > 0:
        worker_argv.append(f"--max-tasks-per-child={max_tasks_per_child}")
    logger.info(f"准备启动 Celery Worker, 参数: {' '.join(worker_argv)}")

    try:
        celery_app.worker_main(argv=worker_argv)
    except SystemExit:
        logger.info("Celery Worker 已正常停止。")


if __name__ == "__main__":
    main()
