"""module_contact 验证码服务测试(REQ-010): 双通道路由/冷却/一次一用生命周期, 零外部依赖

通道(邮件/短信)以打桩替换, 缓存走测试环境 fakeredis, 全程零外网。
"""

import uuid

import pytest

from module_contact.service.verify_code import VerifyCodeService


class _StubChannel:
    """通道桩: 记录调用并返回发送成功"""

    def __init__(self):
        self.calls: list[tuple] = []

    async def send_code(self, target: str, code: str, ttl_minutes: int) -> bool:
        self.calls.append((target, code, ttl_minutes))
        return True


class _FailChannel:
    """通道桩: 恒定发送失败"""

    async def send_code(self, target: str, code: str, ttl_minutes: int) -> bool:
        return False


def _make_service(email=None, sms=None) -> tuple[VerifyCodeService, _StubChannel, _StubChannel]:
    email = email or _StubChannel()
    sms = sms or _StubChannel()
    return VerifyCodeService(email_service=email, sms_service=sms), email, sms


async def test_email_route_and_verify_lifecycle():
    """邮箱目标走邮件通道; 验证码错误被拒/正确通过/通过后立即失效(一次一用)"""
    target = f"audit_{uuid.uuid4().hex[:8]}@test.com"
    service, email, _ = _make_service()
    assert await service.send(target) is True

    sent_target, code, ttl_min = email.calls[-1]
    assert sent_target == target
    assert code.isdigit() and len(code) == 6
    assert ttl_min >= 1

    with pytest.raises(ValueError):
        await service.verify(target, "000000")
    await service.verify(target, code)
    with pytest.raises(ValueError):
        await service.verify(target, code)


async def test_phone_route_to_sms():
    """手机号目标自动路由短信通道"""
    phone = "13" + "".join(c for c in uuid.uuid4().hex if c.isdigit()).ljust(9, "0")[:9]
    service, _, sms = _make_service()
    assert await service.send(phone) is True
    assert sms.calls and sms.calls[-1][0] == phone


async def test_send_cooldown():
    """同一目标 60s 冷却期内重复发送被拒"""
    target = f"cd_{uuid.uuid4().hex[:8]}@test.com"
    service, _, _ = _make_service()
    assert await service.send(target) is True
    with pytest.raises(ValueError, match="稍后再试"):
        await service.send(target)


async def test_scene_isolation():
    """不同业务场景缓存键隔离: register 的验证码不能校验 login 场景"""
    target = f"sc_{uuid.uuid4().hex[:8]}@test.com"
    service, _, _ = _make_service()
    await service.send(target, scene="register")
    code = service.email_service.calls[-1][1]
    with pytest.raises(ValueError):
        await service.verify(target, code, scene="login")
    await service.verify(target, code, scene="register")


async def test_invalid_target_rejected():
    """非邮箱/手机号目标直接拒绝"""
    service, _, _ = _make_service()
    with pytest.raises(ValueError, match="邮箱或手机号"):
        await service.send("not-a-valid-target")


async def test_send_failure_not_cached():
    """通道发送失败: 抛错且不落缓存(冷却未占用, 换正常通道可立即重试)"""
    target = f"fail_{uuid.uuid4().hex[:8]}@test.com"
    service = VerifyCodeService(email_service=_FailChannel())
    with pytest.raises(ValueError, match="发送失败"):
        await service.send(target)
    # 同目标换正常通道立即重试成功(证明失败未写冷却键)
    service.email_service = _StubChannel()
    assert await service.send(target) is True
