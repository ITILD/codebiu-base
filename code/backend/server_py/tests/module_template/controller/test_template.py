"""module_template 接口层 CRUD 集成测试

覆盖: 创建/详情/部分更新/单删/批量删/分页列表/无限滚动/参数校验/404 场景
注: template 表为共享库表, 断言只针对本用例创建的数据(带唯一后缀), 测完清理
"""

import uuid

BASE = "/template/templates"


def _payload(**overrides) -> dict:
    payload = {
        "name": "接口测试模板",
        "description": "pytest 自动创建",
        "value": 1,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


async def _create(client, **overrides) -> str:
    """创建一条模板并返回其 ID"""
    resp = await client.post(BASE, json=_payload(**overrides))
    assert resp.status_code == 201, resp.text
    template_id = resp.json()
    assert isinstance(template_id, str) and template_id
    return template_id


# ==================== 创建 ====================
async def test_create_returns_201_with_id(client):
    template_id = await _create(client)
    try:
        detail = (await client.get(f"{BASE}/{template_id}")).json()
        assert detail["id"] == template_id
        assert detail["value"] == 1
        assert detail["is_active"] is True
    finally:
        await client.delete(f"{BASE}/{template_id}")


async def test_create_name_over_max_length_rejected(client):
    resp = await client.post(BASE, json=_payload(name="x" * 101))
    assert resp.status_code == 422


async def test_create_description_over_max_length_rejected(client):
    resp = await client.post(BASE, json=_payload(description="x" * 501))
    assert resp.status_code == 422


# ==================== 详情 ====================
async def test_get_not_found_returns_404(client):
    resp = await client.get(f"{BASE}/{uuid.uuid4().hex}")
    assert resp.status_code == 404
    assert "模板不存在" in resp.text


# ==================== 单条 CRUD 流 ====================
async def test_template_crud_flow(client):
    template_id = await _create(client, value=5)
    try:
        # 详情
        resp = await client.get(f"{BASE}/{template_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == template_id
        assert detail["value"] == 5

        # 部分更新: 仅传 value, 其余字段不受影响
        resp = await client.put(f"{BASE}/{template_id}", json={"value": 99})
        assert resp.status_code == 204
        detail = (await client.get(f"{BASE}/{template_id}")).json()
        assert detail["value"] == 99
        assert detail["name"] == "接口测试模板"
        assert detail["is_active"] is True
    finally:
        # 单删 204, 删后 404
        assert (await client.delete(f"{BASE}/{template_id}")).status_code == 204
        assert (await client.get(f"{BASE}/{template_id}")).status_code == 404


async def test_update_not_found_returns_404(client):
    missing = uuid.uuid4().hex
    resp = await client.put(f"{BASE}/{missing}", json={"value": 1})
    assert resp.status_code == 404
    assert missing in resp.text


async def test_delete_not_found_returns_404(client):
    missing = uuid.uuid4().hex
    resp = await client.delete(f"{BASE}/{missing}")
    assert resp.status_code == 404
    assert missing in resp.text


# ==================== 批量删除 ====================
async def _batch_delete(client, ids: list[str]):
    """批量删除辅助: httpx 的 delete() 不支持 json 参数, 统一走 request"""
    return await client.request("DELETE", f"{BASE}/batch", json={"ids": ids})


async def test_batch_delete_skips_missing_ids(client):
    ids = [await _create(client), await _create(client)]
    # 混入不存在的 ID 应静默跳过, 只统计实际删除数
    resp = await _batch_delete(client, [*ids, uuid.uuid4().hex])
    assert resp.status_code == 200
    assert resp.json() == {"deleted_count": 2}
    for template_id in ids:
        assert (await client.get(f"{BASE}/{template_id}")).status_code == 404


async def test_batch_delete_empty_ids_rejected(client):
    resp = await _batch_delete(client, [])
    assert resp.status_code == 422


async def test_batch_delete_blank_id_rejected(client):
    resp = await _batch_delete(client, [uuid.uuid4().hex, "   "])
    assert resp.status_code == 422


async def test_batch_delete_over_max_ids_rejected(client):
    ids = [uuid.uuid4().hex for _ in range(201)]  # 上限 200
    resp = await _batch_delete(client, ids)
    assert resp.status_code == 422


# ==================== 分页列表 ====================
async def test_list_pagination_metadata(client):
    ids = [await _create(client) for _ in range(3)]
    try:
        resp = await client.get(f"{BASE}/list", params={"page": 1, "size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["size"] == 2
        assert data["total"] >= 3
        assert data["pages"] == (data["total"] + 1) // 2
        assert len(data["items"]) == 2
        # 越界页码校验
        assert (await client.get(f"{BASE}/list", params={"page": 0})).status_code == 422
        assert (
            await client.get(f"{BASE}/list", params={"size": 501})
        ).status_code == 422
    finally:
        await _batch_delete(client, ids)


# ==================== 无限滚动 ====================
async def test_scroll_first_page_and_cursor(client):
    ids = [await _create(client) for _ in range(2)]
    try:
        # 首页 limit=1: dao 查 limit+1=2 条(表内至少本用例的 2 条), 必有更多
        resp = await client.get(f"{BASE}/scroll", params={"limit": 1})
        assert resp.status_code == 200
        page1 = resp.json()
        assert len(page1["items"]) == 1
        assert page1["has_more"] is True
        assert page1["last_id"] == page1["items"][0]["id"]

        # 以首页游标续拉: 升序推进, 与首页无交集
        resp = await client.get(
            f"{BASE}/scroll", params={"limit": 1, "last_id": page1["last_id"]}
        )
        assert resp.status_code == 200
        page2 = resp.json()
        page2_ids = {item["id"] for item in page2["items"]}
        assert page1["last_id"] not in page2_ids
    finally:
        await _batch_delete(client, ids)


async def test_scroll_invalid_cursor_returns_404(client):
    resp = await client.get(
        f"{BASE}/scroll", params={"limit": 1, "last_id": uuid.uuid4().hex}
    )
    assert resp.status_code == 404
