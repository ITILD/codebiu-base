"""REQ-009 操作审计中间件与查询接口测试

覆盖: 登录落库+密码脱敏 / 写操作落库并记录操作人 / 读操作不落库 / 普通用户无权查询
"""

from common.middleware.audit import audit_recorder


async def _flush():
    """立即落库缓冲中的审计记录(生产环境为攒批/延迟落库)"""
    await audit_recorder.flush_now()


async def _query(client, **params):
    resp = await client.get("/audit_logs/list", params={"size": 50, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_login_audited_and_password_masked(anon_client, client, test_admin):
    """登录属写方法应落库: 记录表单用户名, 密码脱敏为 ***"""
    resp = await anon_client.post(
        "/authorization/auth/login",
        data={"username": test_admin["username"], "password": test_admin["password"]},
    )
    assert resp.status_code == 200, resp.text
    await _flush()

    data = await _query(client, keyword="/auth/login", username=test_admin["username"])
    assert data["total"] >= 1
    entry = data["items"][0]
    assert entry["method"] == "POST"
    assert entry["username"] == test_admin["username"]
    digest = entry["params_digest"] or ""
    assert "***" in digest
    assert test_admin["password"] not in digest


async def test_write_op_audited_with_operator(client, test_admin):
    """写操作(带鉴权依赖的 PUT /auth/me)应落库并记录操作人(user_id)

    注: dict 系列接口历史设计无鉴权依赖, 无法验证操作人, 故选自助资料接口
    (提交与注册相同的昵称, 不产生真实数据变更)
    """
    resp = await client.put(
        "/authorization/auth/me",
        json={"nickname": "测试管理员"},
    )
    assert resp.status_code == 200, resp.text
    await _flush()

    data = await _query(client, keyword="/auth/me", method="PUT")
    assert data["total"] >= 1
    entry = data["items"][0]
    assert entry["user_id"] == test_admin["id"]
    assert "测试管理员" in (entry["params_digest"] or "")


async def test_read_op_not_audited(client):
    """读操作(GET)不产生审计记录"""
    resp = await client.get("/dict_types/list", params={"page": 1, "size": 5})
    assert resp.status_code == 200
    await _flush()

    data = await _query(client, method="GET")
    assert data["total"] == 0


async def test_query_requires_admin(user_client):
    """普通用户(无 sys:audit:read)查询审计被拒 403"""
    resp = await user_client.get("/audit_logs/list")
    assert resp.status_code == 403
