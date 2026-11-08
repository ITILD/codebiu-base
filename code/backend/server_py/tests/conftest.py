"""conftest.py pytest 默认测试配置文件
所有同目录测试文件运行前都会执行 conftest.py，不需要 import 导入。

基础设施:
- _app_lifespan: session 级触发完整 lifespan(建表/casbin/默认管理员引导),测试完关闭连接
- test_admin: session 级注册专用测试管理员并绑定 admin 角色(绝不复用真实 admin 账户)
- admin_headers: 测试管理员真实登录,返回 Bearer 鉴权头(走完整 JWT+casbin 链路)
- client: 带管理员鉴权的 httpx 异步客户端(ASGITransport 直连 app,无需启动服务器)
- anon_client: 匿名客户端(测登录/注册/401 场景)

约定:
- asyncio 默认 session loop(lifespan 与测试同 loop,asyncpg 连接池不跨 loop)
- 测试数据一律带时间戳唯一后缀,测完清理,不依赖执行顺序
- 禁止用真实 admin 账户执行写操作类用例(自助资料/头像等会覆盖持久数据)
"""
from __future__ import annotations

import hashlib
import logging
import sys
import time
import uuid
from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

# Windows 下切换 Selector 事件循环(psycopg 异步模式不支持 ProactorEventLoop,
# 必须在 pytest-asyncio 创建 session loop 之前设置策略)
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from common.config.path import DIR_LOG
from common.config.index import is_dev
from common.utils.log.logging_rich import LoggingRich

# ==================== 日志 ====================
dev_log = LoggingRich(DIR_LOG, is_dev)
dev_log.setup()
logger = logging.getLogger(__name__)
logger.info("test log is set up ok")
logger.info("运行环境: %s", "测试 (tests)")

BASE_URL = "http://test"
TEST_ADMIN_PASSWORD = "Test123456"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _app_lifespan():
    """session 级: 触发完整 lifespan(连接池/建表/casbin/管理员引导),结束后关闭"""
    from app import app

    async with app.router.lifespan_context(app):
        logger.info("app lifespan started (tables/casbin/admin ready)")
        yield
    logger.info("app lifespan closed")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _disable_register_verify(_app_lifespan):
    """测试环境关闭注册邮箱/短信验证开关

    生产/开发动态配置可能已开启注册验证码; 测试批量注册账户时不应依赖真实
    SMTP/短信通道, 故在会话内把认证服务读取的两个开关固定为关闭(不改数据库)。
    """
    from module_authorization.service import auth as auth_module

    patcher = pytest.MonkeyPatch()

    async def _always_false() -> bool:
        return False

    patcher.setattr(auth_module, "email_verify_enabled", _always_false)
    patcher.setattr(auth_module, "sms_verify_enabled", _always_false)
    try:
        yield
    finally:
        patcher.undo()


class _MemoryStorage:
    """内存版存储(满足 StorageInterface 协议; 非 S3 子类 → 上传走 proxy 中转路径)

    测试专用: 数据全程驻留内存, 会话结束自动丢弃, 零外部依赖;
    分片合并与服务端保存时以重算的真实 SHA-256 归位(与历史 local 实现同语义)。
    """

    def __init__(self):
        self._objects: dict[str, bytes] = {}
        self._uploads: dict[str, dict[int, bytes]] = {}
        self._seq = 0

    async def save(self, key, data) -> str:
        if isinstance(data, bytes):
            self._objects[key] = data
        elif hasattr(data, "read"):  # io.IOBase
            self._objects[key] = data.read()
        elif hasattr(data, "__aiter__"):  # AsyncIterator
            chunks = [c async for c in data]
            self._objects[key] = b"".join(chunks)
        else:
            raise TypeError("Unsupported data type for saving")
        return key

    async def load(self, key: str) -> bytes:
        return self._objects[key]

    async def iter_chunks(self, key: str, chunk_size: int = 8192):
        data = self._objects[key]
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    async def delete(self, key: str) -> bool:
        return self._objects.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def size(self, key: str) -> int:
        return len(self._objects[key])

    async def list(self, prefix: str = "") -> list[str]:
        return sorted(k for k in self._objects if k.startswith(prefix))

    async def create_multipart(
        self, key: str, content_type: str = "application/octet-stream"
    ) -> str:
        self._seq += 1
        uid = f"mem-upload-{self._seq}"
        self._uploads[uid] = {}
        return uid

    async def upload_part(
        self, key: str, upload_id: str, part_number: int, data: bytes
    ) -> dict:
        self._uploads[upload_id][part_number] = data
        return {"part_number": part_number, "etag": str(len(data)), "size": len(data)}

    async def list_parts(self, key: str, upload_id: str) -> list[dict]:
        return [
            {"part_number": n, "etag": str(len(d)), "size": len(d)}
            for n, d in sorted(self._uploads.get(upload_id, {}).items())
        ]

    async def complete_multipart(
        self,
        key: str,
        upload_id: str,
        parts: list[dict],
        expected_hash: str | None = None,
    ) -> tuple[str, int, str]:
        session = self._uploads.pop(upload_id)
        merged = b"".join(
            session[int(p["part_number"])] for p in sorted(parts, key=lambda x: int(x["part_number"]))
        )
        real_hash = hashlib.sha256(merged).hexdigest()
        final_key = f"{real_hash}{Path(key).suffix}"
        self._objects[final_key] = merged
        return real_hash, len(merged), final_key

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        self._uploads.pop(upload_id, None)

    async def presign_put(self, key, upload_id=None, part_number=None, expires=3600):
        return None

    async def presign_get(self, key, expires=3600, download_filename=None):
        return None


@pytest_asyncio.fixture(scope="session", autouse=True)
async def memory_storage_override():
    """session 级: 全局存储替换为内存实现, 保证全部模块测试零外部依赖

    凡经统一文件服务(module_file)读写的测试(文件管理/知识库文档/用户头像等)都不依赖
    外部对象存储(rustfs 等); 注: 直传(direct)模式测试用 FakeS3Storage 经依赖覆盖自行注入,
    不受本覆盖影响。
    """
    import module_file.config.filesystem as fs_config
    from module_file.utils.multi_storage.do.storage_config import (
        StorageConfigFactory,
    )

    cfg = StorageConfigFactory.create(
        "s3", {"max_size": 10, "allowed_extensions": [], "bucket": "test-bucket"}
    )
    fs_config.storage = _MemoryStorage()
    fs_config.storage_config = cfg
    # service/filesystem.py 经 fs_config 模块属性读取 storage/storage_config(无独立引用)
    yield


def _make_client(headers: dict | None = None) -> AsyncClient:
    """构造 ASGI 直连客户端(每次请求独立,避免状态串扰)"""
    from app import app

    return AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE_URL, headers=headers or {}
    )


@pytest_asyncio.fixture(scope="session")
async def test_admin(_app_lifespan, memory_storage_override) -> dict:
    """session 级专用测试管理员: 注册新账号并绑定全局 admin 角色, 测完清理

    历史教训: 早期 client 直接复用真实 admin 账户, 头像/自助资料用例会覆盖
    admin 的持久数据(avatar 字段被改成测试假文件、旧头像条目被删除、昵称
    邮箱被改写), 导致真实用户头像丢失。故所有管理员写操作均走本账户。
    """
    username = f"pytest_admin_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    async with _make_client() as ac:
        resp = await ac.post(
            "/authorization/auth/register",
            json={"username": username, "password": TEST_ADMIN_PASSWORD, "nickname": "测试管理员"},
        )
    assert resp.status_code == 200, f"测试管理员注册失败: {resp.status_code} {resp.text}"
    user_id = resp.json()["user"]["id"]
    # 绑定全局域 admin 角色(同 ensure_default_admin 引导逻辑)
    from module_authorization.config.casbin_rule import auth_manager

    await auth_manager.enforcer.add_grouping_policy(user_id, "admin", "*")
    yield {"id": user_id, "username": username, "password": TEST_ADMIN_PASSWORD}
    # 会话收尾: 清理头像条目/头像字段 → casbin 规则 → 用户记录
    from module_authorization.dao.user import UserDao
    from module_authorization.service.avatar import AvatarService

    try:
        await AvatarService().delete_avatar(user_id)
    except ValueError:
        pass  # 本会话未上传过头像
    await auth_manager.enforcer.remove_filtered_grouping_policy(0, user_id)
    await UserDao().delete(user_id)
    logger.info(f"测试管理员 {username} 已清理")


@pytest_asyncio.fixture(scope="session")
async def admin_token(test_admin: dict) -> str:
    """管理员登录获取访问令牌(走真实登录链路, 使用专用测试管理员)"""
    async with _make_client() as ac:
        resp = await ac.post(
            "/authorization/auth/login",
            data={"username": test_admin["username"], "password": test_admin["password"]},
        )
    assert resp.status_code == 200, f"测试管理员登录失败: {resp.status_code} {resp.text}"
    return resp.json()["tokens"]["access"]["token"]


@pytest_asyncio.fixture(scope="session")
async def admin_headers(admin_token: str) -> dict:
    """带管理员 Bearer 鉴权头的请求头"""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture(scope="session")
async def normal_user() -> dict:
    """注册一个普通(非管理员)用户, 返回 {username, headers}(测权限收紧/脱敏场景)"""
    suffix = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    username = f"u_{suffix}"
    password = "Test123456"
    async with _make_client() as ac:
        resp = await ac.post(
            "/authorization/auth/register",
            json={"username": username, "password": password, "nickname": "测试普通用户"},
        )
    assert resp.status_code == 200, f"普通用户注册失败: {resp.status_code} {resp.text}"
    token = resp.json()["tokens"]["access"]["token"]
    return {"username": username, "headers": {"Authorization": f"Bearer {token}"}}


@pytest_asyncio.fixture
async def user_client(normal_user: dict) -> AsyncClient:
    """带普通用户鉴权的异步测试客户端(非管理员, 每用例独立实例)"""
    async with _make_client(normal_user["headers"]) as ac:
        yield ac


@pytest_asyncio.fixture
async def client(admin_headers: dict) -> AsyncClient:
    """带管理员鉴权的异步测试客户端(每用例独立实例)"""
    async with _make_client(admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def anon_client() -> AsyncClient:
    """匿名客户端(无鉴权头,测公开端点/401 场景)"""
    async with _make_client() as ac:
        yield ac
