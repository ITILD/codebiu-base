# -*- coding: utf-8 -*-
"""module_authorization 登录安全加固测试(REQ-014)
覆盖: 登录失败锁定(阈值/锁定期拒绝/到期恢复/成功清零/关闭兼容) /
密码强度策略(注册/改密) / 登录二次验证(验证码校验/发送开关) / 登录策略端点
"""
import uuid

import httpx
import pytest

from common.config.db import db_cache
from common.config.dynamic.schemas import LoginSecuritySettings
from module_authorization.service.login_security import LOGIN_FAIL_KEY
from module_contact.config.verify_code import CODE_KEY

AUTH = "/authorization/auth"
CONFIG = "/sys-configs/login_security"
USERS = "/authorization/users"

# 合规测试密码(默认策略 8 位 + 2 类别之上)
STRONG_PASSWORD = "Abc12345"

# 测试锁定配置(阈值 3 / 锁 1 分钟, 缩短窗口)
_LOCK_CFG = {"lock_enabled": True, "max_failed_attempts": 3, "lock_minutes": 1}


async def _update_cfg(client: httpx.AsyncClient, **overrides) -> None:
    """应用登录安全测试配置(走正式配置端点, 同时验证 schema 校验与缓存失效)"""
    data = {**_LOCK_CFG, **overrides}
    resp = await client.put(CONFIG, json={"data": data})
    assert resp.status_code == 204, resp.text


async def _reset_cfg(client: httpx.AsyncClient) -> None:
    """恢复出厂默认(锁定开 5 次/15 分钟, 密码策略与二次验证关)"""
    resp = await client.put(
        CONFIG, json={"data": LoginSecuritySettings().model_dump()}
    )
    assert resp.status_code == 204, resp.text


async def _register(
    client: httpx.AsyncClient, password: str = STRONG_PASSWORD
) -> tuple[str, str, str, str]:
    """注册测试用户, 返回 (username, password, user_id, access_token)"""
    username = f"lock_{uuid.uuid4().hex[:10]}"
    email = f"{username}@test.local"
    resp = await client.post(
        f"{AUTH}/register",
        json={"username": username, "password": password, "email": email},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return username, password, body["user"]["id"], body["tokens"]["access"]["token"]


async def _cleanup_user(client: httpx.AsyncClient, username: str, user_id: str) -> None:
    """清理测试用户与登录失败计数缓存键"""
    await db_cache.async_cache.delete(LOGIN_FAIL_KEY.format(username=username))
    resp = await client.delete(f"{USERS}/{user_id}")
    assert resp.status_code == 204, resp.text


async def _login(client: httpx.AsyncClient, username: str, password: str, code: str | None = None):
    data = {"username": username, "password": password}
    if code is not None:
        data["code"] = code
    return await client.post(f"{AUTH}/login", data=data)


@pytest.fixture
async def lock_cfg(client: httpx.AsyncClient):
    """应用锁定测试配置, 用例结束后恢复默认"""
    await _update_cfg(client)
    yield
    await _reset_cfg(client)


async def test_login_policy_endpoint(anon_client: httpx.AsyncClient):
    """登录策略端点匿名可访问, 默认返回二次验证关闭"""
    resp = await anon_client.get(f"{AUTH}/login-policy")
    assert resp.status_code == 200, resp.text
    assert resp.json()["mfa_enabled"] is False


async def test_lock_after_threshold(client: httpx.AsyncClient, lock_cfg):
    """连续失败达阈值后锁定, 锁定期正确密码也被拒, 键过期(到期)自动恢复"""
    username, password, user_id, _ = await _register(client)
    try:
        # 阈值 3 次内: 普通凭据错误
        for _ in range(3):
            resp = await _login(client, username, "wrong-password")
            assert resp.status_code == 401, resp.text
            assert "锁定" not in resp.json()["detail"]
        # 第 4 次正确密码: 锁定拒绝并提示剩余时间
        resp = await _login(client, username, password)
        assert resp.status_code == 401, resp.text
        detail = resp.json()["detail"]
        assert "锁定" in detail and "分钟" in detail, detail
        # 模拟锁定期满: 计数键过期自动恢复
        await db_cache.async_cache.delete(LOGIN_FAIL_KEY.format(username=username))
        resp = await _login(client, username, password)
        assert resp.status_code == 200, resp.text
    finally:
        await _cleanup_user(client, username, user_id)


async def test_success_clears_counter(client: httpx.AsyncClient, lock_cfg):
    """未达阈值的失败计数在成功登录后清零, 不跨轮累计"""
    username, password, user_id, _ = await _register(client)
    try:
        for _ in range(2):
            await _login(client, username, "wrong-password")
        # 2 次(未达阈值 3): 正确密码可登录并清零计数
        resp = await _login(client, username, password)
        assert resp.status_code == 200, resp.text
        # 再错 2 次后仍可登录(若计数未清, 累计 4 次已锁)
        for _ in range(2):
            await _login(client, username, "wrong-password")
        resp = await _login(client, username, password)
        assert resp.status_code == 200, resp.text
    finally:
        await _cleanup_user(client, username, user_id)


async def test_lock_disabled_compatible(client: httpx.AsyncClient, lock_cfg):
    """关闭锁定开关后行为与现状一致: 超阈值失败仍不锁"""
    await _update_cfg(client, lock_enabled=False)
    username, password, user_id, _ = await _register(client)
    try:
        for _ in range(4):
            resp = await _login(client, username, "wrong-password")
            assert resp.status_code == 401
        resp = await _login(client, username, password)
        assert resp.status_code == 200, resp.text
    finally:
        await _cleanup_user(client, username, user_id)


async def test_password_policy_register(client: httpx.AsyncClient, lock_cfg):
    """开启密码策略后弱密码注册被拒(400), 强密码可注册"""
    await _update_cfg(client, password_policy_enabled=True)
    # 弱密码: 7 位(不足 8)且单类别
    resp = await client.post(
        f"{AUTH}/register",
        json={"username": f"weak_{uuid.uuid4().hex[:8]}", "password": "abc1234"},
    )
    assert resp.status_code == 400, resp.text
    assert "密码" in resp.json()["detail"]
    # 合规密码可注册
    username, _, user_id, _ = await _register(client)
    try:
        assert user_id
    finally:
        await _cleanup_user(client, username, user_id)


async def test_password_policy_change_password(client: httpx.AsyncClient, lock_cfg):
    """开启密码策略后改密同规则: 弱密码 400, 合规密码 204"""
    await _update_cfg(client, password_policy_enabled=True)
    username, password, user_id, token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # 弱密码被拒
        resp = await client.put(
            f"{AUTH}/me/password",
            json={"old_password": password, "new_password": "weakpass"},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert "密码" in resp.json()["detail"]
        # 合规密码成功
        resp = await client.put(
            f"{AUTH}/me/password",
            json={"old_password": password, "new_password": "Xyz98765"},
            headers=headers,
        )
        assert resp.status_code == 204, resp.text
    finally:
        await _cleanup_user(client, username, user_id)


async def test_mfa_login_flow(client: httpx.AsyncClient, lock_cfg):
    """开启二次验证后: 无验证码被拒, 正确验证码(邮箱)可登录"""
    await _update_cfg(client, mfa_enabled=True)
    username, password, user_id, _ = await _register(client)
    email = f"{username}@test.local"
    code_key = CODE_KEY.format(scene="login", target=email)
    try:
        # 密码正确但缺验证码
        resp = await _login(client, username, password)
        assert resp.status_code == 401, resp.text
        assert "验证码" in resp.json()["detail"]
        # 直写缓存模拟已发送的邮箱验证码(绕开外部邮件通道)
        await db_cache.async_cache.set(code_key, "654321", ex=300)
        resp = await _login(client, username, password, code="654321")
        assert resp.status_code == 200, resp.text
        # 验证码一次一用: 成功登录已消费, 同码再次登录被拒
        resp = await _login(client, username, password, code="654321")
        assert resp.status_code == 401, resp.text
    finally:
        await db_cache.async_cache.delete(code_key)
        await _cleanup_user(client, username, user_id)


async def test_send_login_code_requires_mfa(client: httpx.AsyncClient, lock_cfg):
    """二次验证关闭时发送登录验证码端点返回 400"""
    resp = await client.post(f"{AUTH}/login/code", json={"username": "admin"})
    assert resp.status_code == 400, resp.text


async def test_lock_error_counts_hint_minutes(client: httpx.AsyncClient, lock_cfg):
    """锁定提示包含剩余分钟数(向上取整至少 1 分钟)"""
    username, password, user_id, _ = await _register(client)
    try:
        for _ in range(3):
            await _login(client, username, "wrong-password")
        resp = await _login(client, username, password)
        detail = resp.json()["detail"]
        assert "请约 1 分钟" in detail, detail
    finally:
        await _cleanup_user(client, username, user_id)
