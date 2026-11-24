"""权限加固回归测试

覆盖本轮修复: 匿名/越权接口收紧(会话IDOR、库结构操作、主机信息、字典写、
模板CRUD、AI管理接口)与权限码默认授予(websearch)。
"""

BASE_DB = "/db"
BASE_STATUS = "/server-status"
BASE_DICT = "/dict_types"
BASE_CONV = "/rag/conversations"
BASE_TPL = "/template/templates"


async def test_db_struct_ops_require_admin(anon_client, user_client, client):
    """库结构操作(建表/重置)需登录且仅全局管理员; 清单接口需 main:db:read"""
    # 匿名 401 / 普通用户 403
    for c in (anon_client, user_client):
        resp = await c.get(f"{BASE_DB}/create")
        assert resp.status_code in (401, 403)
        resp = await c.get(f"{BASE_DB}/reset")
        assert resp.status_code in (401, 403)
    # 管理员可访问(建表幂等; reset 破坏性大, 仅验证鉴权通过的只读清单)
    resp = await client.get(f"{BASE_DB}/tables")
    assert resp.status_code == 200, resp.text
    # 普通用户默认拥有 main:dict/main:db 的 read(基础资源只读)
    resp = await user_client.get(f"{BASE_DB}/tables")
    assert resp.status_code == 200, resp.text


async def test_server_status_requires_login(anon_client, user_client):
    """主机状态/硬件/网络信息不再匿名可读"""
    for path in ("/cache", "/sys-info", "/hardware-status", "/network-status"):
        resp = await anon_client.get(f"{BASE_STATUS}{path}")
        assert resp.status_code in (401, 403), f"{path} 匿名可读"
    resp = await user_client.get(f"{BASE_STATUS}/sys-info")
    assert resp.status_code == 200, resp.text


async def test_dict_write_requires_permission(anon_client, user_client):
    """字典读默认放开(user 默认策略), 写操作需 main:dict:create(普通用户 403)"""
    resp = await anon_client.get(f"{BASE_DICT}/list")
    assert resp.status_code in (401, 403)
    resp = await user_client.get(f"{BASE_DICT}/list")
    assert resp.status_code == 200, resp.text
    resp = await user_client.post(
        f"{BASE_DICT}",
        json={"type_code": "pw_test", "type_name": "越权测试"},
    )
    assert resp.status_code == 403, resp.text


async def test_conversation_idor_blocked(anon_client, user_client, client):
    """他人会话不可读改删: 匿名 401, 非属主普通用户 403, 属主/管理员放行"""
    resp = await client.post(
        f"{BASE_CONV}", json={"title": "权限加固测试会话"}
    )
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()  # create 直接返回会话ID字符串

    resp = await anon_client.get(f"{BASE_CONV}/{conv_id}")
    assert resp.status_code in (401, 403)
    resp = await user_client.get(f"{BASE_CONV}/{conv_id}")
    assert resp.status_code == 403, resp.text
    resp = await user_client.get(f"{BASE_CONV}/{conv_id}/messages")
    assert resp.status_code == 403, resp.text
    resp = await user_client.delete(f"{BASE_CONV}/{conv_id}")
    assert resp.status_code == 403, resp.text
    # 管理员(属主)可正常读删
    resp = await client.get(f"{BASE_CONV}/{conv_id}")
    assert resp.status_code == 200, resp.text
    resp = await client.delete(f"{BASE_CONV}/{conv_id}")
    assert resp.status_code == 204, resp.text


async def test_template_crud_requires_login(anon_client, user_client):
    """模板 CRUD 统一要求登录(路由级依赖)"""
    resp = await anon_client.get(f"{BASE_TPL}/list")
    assert resp.status_code in (401, 403)
    resp = await user_client.get(f"{BASE_TPL}/list")
    assert resp.status_code == 200, resp.text


async def test_ai_admin_endpoints_require_login(anon_client, user_client):
    """AI 配置校验/能力测试/缓存清理接口需登录(公开 chat 工具接口除外)"""
    resp = await anon_client.post("/ai/llm/check-config-by-model-id?model_id=x")
    assert resp.status_code in (401, 403)
    resp = await anon_client.delete("/ai/llm/cache/whatever")
    assert resp.status_code in (401, 403)
    resp = await anon_client.delete("/ai/llm/cache")
    assert resp.status_code in (401, 403)
    # 登录后通过鉴权(model_id 不存在时返回业务错误而非 401/403)
    resp = await user_client.delete("/ai/llm/cache/nonexistent")
    assert resp.status_code not in (401, 403), resp.text


async def test_websearch_default_policy_for_user(normal_user):
    """普通用户默认拥有 websearch:search:read(修复 main:search 死节点导致授权无效)"""
    async with _anon() as ac:
        resp = await ac.get(
            "/authorization/auth/me-permissions",
            headers=normal_user["headers"],
        )
    assert resp.status_code == 200, resp.text
    perms = resp.json().get("permissions") or []
    assert any(p.startswith("websearch:search") for p in perms), perms
    assert not any(p.startswith("main:search") for p in perms), perms


def _anon():
    """构造匿名客户端(延迟导入避免模块级初始化)"""
    from httpx import ASGITransport, AsyncClient

    from app import app
    from tests.conftest import BASE_URL

    return AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL)
