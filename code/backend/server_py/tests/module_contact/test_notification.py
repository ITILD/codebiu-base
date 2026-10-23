"""module_contact 通知中心测试(REQ-011): 三通道路由/降级/自助接口/任务终态埋点, 零外部依赖

外部通道(邮件/短信)以打桩替换, 与 test_verify_code 同模式; 用户联系方式
直接改 User 行(测后恢复), 站内信/订阅/任务行测完自清理。
"""

import asyncio
import uuid

import pytest

from common.config.db import db_manager
from module_contact.dao.notification import ContactMessageDao, ContactSubscriptionDao
from module_contact.do.notification import CHANNEL_EMAIL, CHANNEL_INAPP, CHANNEL_SMS
from module_contact.service.notification import NotificationService
from module_task.do.task import QueueTaskStatus, TaskQueue
from module_task.tasks import _notify_tasks, update_task_fields


class _StubChannel:
    """外部通道桩: 记录调用并返回发送成功"""

    def __init__(self):
        self.calls: list[tuple] = []

    async def send_notification(self, target: str, title: str, content: str = "") -> bool:
        self.calls.append((target, title, content))
        return True


def _make_service() -> tuple[NotificationService, _StubChannel, _StubChannel]:
    email, sms = _StubChannel(), _StubChannel()
    service = NotificationService(ContactMessageDao(), ContactSubscriptionDao(), email, sms)
    return service, email, sms


@pytest.fixture
async def clean_notify_state(test_admin: dict):
    """用例级数据隔离: 清空测试管理员站内信与订阅(测试库跨运行持久)"""
    user_id = test_admin["id"]
    yield user_id
    await ContactMessageDao().clear(user_id)
    await ContactSubscriptionDao().delete_for_user(user_id)


async def _set_user_contact(user_id: str, email: str | None, phone: str | None) -> None:
    """直接改 User 行联系方式(测后恢复为 None, 不污染持久账户)"""
    from module_authorization.do.user import User

    async with db_manager.db_rel.session_factory() as session:
        user = await session.get(User, user_id)
        user.email, user.phone = email, phone
        session.add(user)
        await session.commit()


# ################ 服务级: 三通道路由与降级 ################

async def test_notify_inapp_only(clean_notify_state):
    """无订阅: 站内必达, 外部通道不发送"""
    user_id = clean_notify_state
    service, email, sms = _make_service()
    msg = await service.notify(user_id, "task_done", "任务成功: demo", "已完成")
    assert msg.channels == [CHANNEL_INAPP]
    assert msg.is_read is False
    assert email.calls == [] and sms.calls == []


async def test_notify_email_subscribed(clean_notify_state):
    """订阅邮件 + 已绑定邮箱: 站内 + 邮件双通道"""
    user_id = clean_notify_state
    await _set_user_contact(user_id, "notify@test.com", None)
    try:
        service, email, sms = _make_service()
        await service.set_subscription(user_id, "task_done", CHANNEL_EMAIL, True)
        msg = await service.notify(user_id, "task_done", "任务成功: demo", "已完成")
        assert CHANNEL_INAPP in msg.channels and CHANNEL_EMAIL in msg.channels
        assert email.calls and email.calls[-1][0] == "notify@test.com"
        assert sms.calls == []
    finally:
        await _set_user_contact(user_id, None, None)


async def test_notify_email_but_no_address(clean_notify_state):
    """订阅邮件但未绑定邮箱: 联系方式缺失自动降级仅站内"""
    user_id = clean_notify_state
    service, email, _ = _make_service()
    await service.set_subscription(user_id, "task_done", CHANNEL_EMAIL, True)
    msg = await service.notify(user_id, "task_done", "任务成功: demo")
    assert msg.channels == [CHANNEL_INAPP]
    assert email.calls == []


async def test_notify_sms_subscribed(clean_notify_state):
    """订阅短信 + 已绑定手机: 站内 + 短信双通道"""
    user_id = clean_notify_state
    await _set_user_contact(user_id, None, "13800001111")
    try:
        service, _, sms = _make_service()
        await service.set_subscription(user_id, "task_done", CHANNEL_SMS, True)
        msg = await service.notify(user_id, "task_done", "任务成功: demo")
        assert CHANNEL_SMS in msg.channels
        assert sms.calls and sms.calls[-1][0] == "13800001111"
    finally:
        await _set_user_contact(user_id, None, None)


async def test_set_subscription_validation(clean_notify_state):
    """非法通知类型/通道被拒"""
    user_id = clean_notify_state
    service, _, _ = _make_service()
    from common.utils.fastapi_ex.exceptions import BusinessError

    with pytest.raises(BusinessError, match="未注册"):
        await service.set_subscription(user_id, "not_exist", CHANNEL_EMAIL, True)
    with pytest.raises(BusinessError, match="非法"):
        await service.set_subscription(user_id, "task_done", CHANNEL_INAPP, True)


# ################ 接口级: 站内信自助操作 ################

async def test_notification_api_flow(client, clean_notify_state):
    """列表/未读数/已读/全部已读/清空 全链路(登录即可, 无管理权限节点)"""
    user_id = clean_notify_state
    service, _, _ = _make_service()
    await service.notify(user_id, "task_done", "通知A", "a")
    await service.notify(user_id, "task_done", "通知B", "b")

    resp = await client.get("/contact/notifications/list", params={"page": 1, "size": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    first_id = body["items"][0]["id"]

    resp = await client.get("/contact/notifications/unread-count")
    assert resp.status_code == 200 and resp.json()["count"] == 2

    resp = await client.put(f"/contact/notifications/{first_id}/read")
    assert resp.status_code == 204
    resp = await client.get("/contact/notifications/unread-count")
    assert resp.json()["count"] == 1

    resp = await client.put("/contact/notifications/read-all")
    assert resp.status_code == 204
    resp = await client.get("/contact/notifications/unread-count")
    assert resp.json()["count"] == 0

    resp = await client.delete("/contact/notifications")
    assert resp.status_code == 204
    resp = await client.get("/contact/notifications/list", params={"page": 1, "size": 10})
    assert resp.json()["total"] == 0


async def test_subscription_api_flow(client, clean_notify_state):
    """订阅矩阵: 默认关闭 → 开启邮件 → 状态回读为开启"""
    resp = await client.get("/contact/notifications/subscriptions")
    assert resp.status_code == 200
    matrix = resp.json()
    assert matrix, "订阅矩阵不应为空"
    assert all(row["enabled"] is False for row in matrix)

    resp = await client.put(
        "/contact/notifications/subscriptions",
        json={"notify_type": "task_done", "channel": "email", "enabled": True},
    )
    assert resp.status_code == 200 and resp.json()["enabled"] is True

    resp = await client.get("/contact/notifications/subscriptions")
    states = {(r["notify_type"], r["channel"]): r["enabled"] for r in resp.json()}
    assert states[("task_done", "email")] is True
    assert states[("task_done", "sms")] is False


async def test_notification_requires_login(anon_client):
    """通知接口未登录 401"""
    resp = await anon_client.get("/contact/notifications/unread-count")
    assert resp.status_code == 401


# ################ 埋点: 任务终态通知 ################

async def _wait_notify_tasks(timeout: float = 5.0) -> None:
    """等待终态通知后台任务全部完成(轮询引用集清空)"""
    deadline = asyncio.get_event_loop().time() + timeout
    while _notify_tasks and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)


async def _make_task(user_id: str, status: str = QueueTaskStatus.RUNNING) -> str:
    """直插任务行(不经 create 派发链路, 避免 local 引擎真的执行任务)"""
    async with db_manager.db_rel.session_factory() as session:
        task = TaskQueue(
            name=f"通知测试任务-{uuid.uuid4().hex[:6]}",
            task_type="demo_document",
            user_id=user_id,
            status=status,
        )
        session.add(task)
        await session.commit()
        return task.id


async def _delete_task(task_id: str) -> None:
    async with db_manager.db_rel.session_factory() as session:
        task = await session.get(TaskQueue, task_id)
        if task:
            await session.delete(task)
            await session.commit()


async def test_task_finished_notifies_creator(client, clean_notify_state):
    """update_task_fields 写入成功终态 → 后台生成 task_done 站内信"""
    user_id = clean_notify_state
    task_id = await _make_task(user_id)
    try:
        await update_task_fields(task_id, status=QueueTaskStatus.SUCCESS, set_finished=True)
        await _wait_notify_tasks()
        resp = await client.get("/contact/notifications/list", params={"page": 1, "size": 10})
        titles = [item["title"] for item in resp.json()["items"]]
        assert any(t.startswith("任务成功: 通知测试任务-") for t in titles)
    finally:
        await _delete_task(task_id)


async def test_task_cancelled_no_notify(clean_notify_state):
    """取消终态不触发通知"""
    user_id = clean_notify_state
    task_id = await _make_task(user_id)
    try:
        await update_task_fields(task_id, status=QueueTaskStatus.CANCELLED, set_finished=True)
        await _wait_notify_tasks()
        assert not _notify_tasks
        dao = ContactMessageDao()
        assert await dao.count(user_id) == 0
    finally:
        await _delete_task(task_id)
