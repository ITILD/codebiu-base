"""REQ-012 周期调度测试: cron 解析单测 + 调度扫描派发/热更/接口用例(零外网)"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

# ################ cron 解析器单测(纯函数) ################
from module_task.utils.cron import CronError, next_fire, parse_cron


def _t(
    minute: int = 0,
    hour: int = 0,
    day: int = 1,
    month: int = 6,
    year: int = 2026,
    second: int = 0,
) -> datetime:
    """基准时刻构造(2026-06-01 为周一)"""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


class TestCronParse:
    def test_field_count(self):
        with pytest.raises(CronError):
            parse_cron("* * * *")  # 少一字段
        with pytest.raises(CronError):
            parse_cron("* * * * * *")  # 多一字段

    def test_value_out_of_range(self):
        with pytest.raises(CronError):
            parse_cron("60 * * * *")  # 分钟越界
        with pytest.raises(CronError):
            parse_cron("* 24 * * *")  # 小时越界
        with pytest.raises(CronError):
            parse_cron("* * 0 * *")  # 日下界 1

    def test_syntax_error(self):
        with pytest.raises(CronError):
            parse_cron("*/x * * * *")  # 步进非数字
        with pytest.raises(CronError):
            parse_cron("a * * * *")  # 非数字
        with pytest.raises(CronError):
            parse_cron("5-1 * * * *")  # 范围倒置

    def test_field_sets(self):
        mins, hours, days, months, dows = parse_cron("*/15,45 8-10 1,15 */2 1,0")
        assert mins == {0, 15, 30, 45}
        assert hours == {8, 9, 10}
        assert days == {1, 15}
        assert months == {1, 3, 5, 7, 9, 11}  # */2 从下界 1 起: 奇数月
        assert dows == {1, 7}  # 周日 0 归一化为 7


class TestNextFire:
    def test_every_minute(self):
        assert next_fire("* * * * *", _t(minute=10, second=30)) == _t(minute=11)

    def test_step_minutes(self):
        # 10:07 的下一个 */15 命中是 10:15(顺推法从 10:08 起找)
        assert next_fire("*/15 * * * *", _t(minute=7)) == _t(minute=15)

    def test_daily_4am(self):
        # 06-01 05:00 之后 → 次日 04:00
        assert next_fire("0 4 * * *", _t(hour=5)) == _t(day=2, hour=4)

    def test_weekly_monday(self):
        # 2026-06-01 是周一; 周一 05:00 之后 → 下周一 06-08 04:00
        assert next_fire("0 4 * * 1", _t(hour=5)) == _t(day=8, hour=4)

    def test_monthly_first_day(self):
        # 06-01 05:00 之后 → 07-01 04:00
        assert next_fire("0 4 1 * *", _t(hour=5)) == _t(day=1, month=7, hour=4)

    def test_range_with_step(self):
        # 10:01 之后的小时 8-18/6(={8,14}) → 14:00
        assert next_fire("0 8-18/6 * * *", _t(hour=10, minute=1)) == _t(hour=14)

    def test_single_with_step_semantics(self):
        # "5/20" ≡ "5-59/20" → 5,25,45; 10:30 之后命中 10:45
        assert next_fire("5/20 * * * *", _t(minute=30)) == _t(minute=45)

    def test_strictly_after_with_seconds(self):
        after = _t(minute=10, second=0)
        assert next_fire("* * * * *", after) == _t(minute=11)

    def test_impossible_date_raises(self):
        # 2 月 30 日不存在, 一年内无命中
        with pytest.raises(CronError):
            next_fire("0 0 30 2 *", _t())

    def test_year_rollover(self):
        # 12-31 23:59 之后 → 次年 01-01(顺推跨年)
        base = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
        assert next_fire("* * * * *", base) == datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc)


# ################ compute_next_fire / 定义校验 ################
from module_task.service.schedule import compute_next_fire  # noqa: E402


def test_compute_next_fire_interval():
    base = _t(minute=0)
    assert compute_next_fire(None, 300, base) == base + timedelta(seconds=300)


def test_compute_next_fire_cron_invalid_to_business_error():
    from common.utils.fastapi_ex.exceptions import BusinessError

    with pytest.raises(BusinessError):
        compute_next_fire("bad expr", None, _t())


# ################ 调度扫描派发与热更(库内闭环, 零外网) ################
from module_task.dao.schedule import TaskScheduleDao  # noqa: E402
from module_task.dao.task import TaskQueueDao  # noqa: E402
from module_task.do.schedule import TaskSchedule  # noqa: E402
from module_task.service.schedule import TaskScheduleService  # noqa: E402
from module_task.service.task import TaskQueueService  # noqa: E402


def _service() -> TaskScheduleService:
    return TaskScheduleService(TaskScheduleDao(), TaskQueueService(TaskQueueDao()))


def _make_schedule(
    *,
    cron: str | None = "*/5 * * * *",
    interval: int | None = None,
    enabled: bool = True,
    next_fire_at: datetime | None = None,
) -> TaskSchedule:
    now = datetime.now(timezone.utc)
    return TaskSchedule(
        name="测试调度",
        task_type="sys_audit_purge",
        payload={},
        cron=cron,
        interval_seconds=interval,
        enabled=enabled,
        next_fire_at=next_fire_at or (now - timedelta(minutes=1) if enabled else None),
        created_by="system",
        created_at=now,
        updated_at=now,
    )


class TestScanDispatch:
    """扫描派发用例(测试库跨运行持久, 用例自建调度须自清理; 断言只针对自建调度)"""

    async def test_due_schedule_fires_and_advances(self):
        """到期调度被派发: 生成 task_queue 记录 + 回写快照 + 推进下次触发"""
        dao = TaskScheduleDao()
        schedule = _make_schedule()
        schedule.id = await dao.add(schedule)
        try:
            await _service().scan_due_and_dispatch()

            refreshed = await dao.get(schedule.id)  # type: ignore[arg-type]
            assert refreshed is not None
            assert refreshed.last_task_id  # 已回写任务ID
            assert refreshed.last_status == "ok"
            assert refreshed.last_fired_at is not None
            # 下次触发已推进到未来(*/5 语义: 未来 5 分钟内)
            assert refreshed.next_fire_at is not None
            assert refreshed.next_fire_at > datetime.now(timezone.utc) - timedelta(seconds=1)
            # 任务记录真实生成(local 引擎进程内执行)
            task = await TaskQueueDao().get(refreshed.last_task_id)
            assert task is not None
            assert task.task_type == "sys_audit_purge"
            assert task.payload.get("_schedule_id") == schedule.id
        finally:
            await dao.delete(schedule.id)  # type: ignore[arg-type]

    async def test_disabled_schedule_not_fired(self):
        """停用调度即使到期也不触发(只校验自建调度未被派发)"""
        dao = TaskScheduleDao()
        schedule = _make_schedule(enabled=False)
        schedule.id = await dao.add(schedule)
        try:
            await _service().scan_due_and_dispatch()

            refreshed = await dao.get(schedule.id)  # type: ignore[arg-type]
            assert refreshed is not None
            assert refreshed.last_task_id is None
        finally:
            await dao.delete(schedule.id)  # type: ignore[arg-type]

    async def test_future_schedule_not_fired(self):
        """未到期(下次触发在未来)不触发"""
        dao = TaskScheduleDao()
        schedule = _make_schedule(next_fire_at=datetime.now(timezone.utc) + timedelta(hours=1))
        schedule.id = await dao.add(schedule)
        try:
            await _service().scan_due_and_dispatch()

            refreshed = await dao.get(schedule.id)  # type: ignore[arg-type]
            assert refreshed is not None
            assert refreshed.last_task_id is None
        finally:
            await dao.delete(schedule.id)  # type: ignore[arg-type]

    async def test_interval_drift_free_advance(self):
        """固定间隔触发后以计划时刻为基准推进(不累积漂移)"""
        dao = TaskScheduleDao()
        planned = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1)
        schedule = _make_schedule(cron=None, interval=3600, next_fire_at=planned)
        schedule.id = await dao.add(schedule)
        try:
            await _service().scan_due_and_dispatch()

            refreshed = await dao.get(schedule.id)  # type: ignore[arg-type]
            assert refreshed is not None
            # 推进基准是 planned 而非当前时刻: next = planned + 3600s
            assert refreshed.next_fire_at == planned + timedelta(seconds=3600)
        finally:
            await dao.delete(schedule.id)  # type: ignore[arg-type]


# ################ 接口层(鉴权/校验/CRUD/触发) ################
class TestScheduleApi:
    async def test_presets_and_list(self, client):
        resp = await client.get("/task/schedules/presets")
        assert resp.status_code == 200
        assert {p["key"] for p in resp.json()} >= {"every_minute", "daily_4am"}

        resp = await client.get("/task/schedules/list")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1  # 内置示例: 审计日志周期清理(启动播种)
        assert any(s["task_type"] == "sys_audit_purge" for s in body["items"])

    async def test_requires_login(self, anon_client):
        resp = await anon_client.get("/task/schedules/list")
        assert resp.status_code == 401

    async def test_create_update_toggle_flow(self, client):
        """创建 → 列表可见 → 改周期热更 → 立即触发 → 删除 全链路"""
        # 创建(启用, 每小时)
        resp = await client.post(
            "/task/schedules",
            json={
                "name": "接口测试调度",
                "task_type": "sys_audit_purge",
                "payload": {},
                "cron": "0 * * * *",
                "interval_seconds": None,
                "enabled": True,
                "remark": None,
            },
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["enabled"] is True
        assert created["next_fire_at"] is not None
        sid = created["id"]

        # 改周期(interval 二选一)并停用 → 热更: next_fire_at 清空
        resp = await client.put(
            f"/task/schedules/{sid}",
            json={
                "name": "接口测试调度",
                "task_type": "sys_audit_purge",
                "payload": {},
                "cron": None,
                "interval_seconds": 7200,
                "enabled": False,
                "remark": None,
            },
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["interval_seconds"] == 7200
        assert updated["enabled"] is False
        assert updated["next_fire_at"] is None

        # 重新启用 → next_fire_at 重算
        resp = await client.put(
            f"/task/schedules/{sid}",
            json={
                "name": "接口测试调度",
                "task_type": "sys_audit_purge",
                "payload": {},
                "cron": None,
                "interval_seconds": 7200,
                "enabled": True,
                "remark": None,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["next_fire_at"] is not None

        # 立即触发(不影响周期节奏)
        resp = await client.post(f"/task/schedules/{sid}/trigger")
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["task_id"]
        assert task_id

        # 删除后再操作 → 404
        resp = await client.delete(f"/task/schedules/{sid}")
        assert resp.status_code == 204, resp.text
        resp = await client.put(
            f"/task/schedules/{sid}",
            json={
                "name": "x", "task_type": "sys_audit_purge", "payload": {},
                "cron": "0 * * * *", "interval_seconds": None,
                "enabled": False, "remark": None,
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_create_validation(self, client):
        base = {
            "name": "非法调度",
            "task_type": "sys_audit_purge",
            "payload": {},
            "enabled": False,
            "remark": None,
        }
        # cron 与 interval 同时提供 → 400
        resp = await client.post(
            "/task/schedules", json={**base, "cron": "0 * * * *", "interval_seconds": 3600}
        )
        assert resp.status_code == 400, resp.text
        # 都不提供 → 400
        resp = await client.post(
            "/task/schedules", json={**base, "cron": None, "interval_seconds": None}
        )
        assert resp.status_code == 400, resp.text
        # interval < 60 → 400
        resp = await client.post(
            "/task/schedules", json={**base, "cron": None, "interval_seconds": 30}
        )
        assert resp.status_code == 400, resp.text
        # 类型未注册 → 400
        resp = await client.post(
            "/task/schedules",
            json={**base, "task_type": "not_exist", "cron": "0 * * * *", "interval_seconds": None},
        )
        assert resp.status_code == 400, resp.text
        # cron 语法非法 → 400
        resp = await client.post(
            "/task/schedules", json={**base, "cron": "bad", "interval_seconds": None}
        )
        assert resp.status_code == 400, resp.text

    async def test_normal_user_forbidden(self, user_client):
        resp = await user_client.get("/task/schedules/list")
        assert resp.status_code == 403


# ################ local 调度循环冒烟(启动即停, 验证可运行) ################
class TestSchedulerLoop:
    async def test_start_and_stop(self):
        from module_task.tasks import scheduler as sched

        sched.start_scheduler()
        assert sched._loop_task is not None and not sched._loop_task.done()
        await asyncio.sleep(0.05)  # 让循环跑过首轮休眠
        await sched.stop_scheduler()
        assert sched._loop_task is None or sched._loop_task.done()

        # 唤醒未启动循环时静默(不抛异常)
        sched.wake_scheduler()
