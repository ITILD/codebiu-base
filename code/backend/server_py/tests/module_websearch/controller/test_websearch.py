"""module_websearch 冒烟测试(REQ-010): 引擎列表/参数校验/鉴权链路, 全程零外网"""

async def test_engines_list_admin(client):
    """管理员查询引擎列表: 200 且包含内置引擎元信息(仅读动态配置, 不发网络请求)"""
    resp = await client.get("/websearch/engines")
    assert resp.status_code == 200, resp.text
    engines = resp.json()
    assert isinstance(engines, list) and len(engines) >= 4
    names = {e["name"] for e in engines}
    assert {"anysearch", "duckduckgo", "tavily", "firecrawl"} <= names


async def test_engines_list_requires_login(anon_client):
    """匿名访问引擎列表: 401(鉴权链路冒烟)"""
    resp = await anon_client.get("/websearch/engines")
    assert resp.status_code == 401


async def test_search_param_validation(client):
    """搜索参数校验冒烟(零外网): 空查询/非法引擎均 422, 不触发真实搜索"""
    resp_empty = await client.post("/websearch/search", json={"query": ""})
    assert resp_empty.status_code == 422

    resp_engine = await client.post(
        "/websearch/search", json={"query": "测试", "engine": "not_exist"}
    )
    assert resp_engine.status_code == 422
