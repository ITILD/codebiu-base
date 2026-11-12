"""static_func 注册表与能力解析测试(REQ-018 批次 1)

纯函数约定把关: 实现 zero-I/O(同输入必同输出), 由 monkeypatch 网络/文件 API
断言未被触碰(设计 §2.2 纯函数约定)。
"""

import pytest


class TestStaticFunctions:
    """内置 static_func: 纯度 + 行为"""

    def test_content_hash_deterministic(self):
        from module_ai.functions import builtin

        assert builtin.content_hash(b"abc") == builtin.content_hash(b"abc")
        assert len(builtin.content_hash(b"abc")) == 64  # sha256 hex
        assert builtin.content_hash(b"abc") != builtin.content_hash(b"abd")
        with pytest.raises(ValueError):
            builtin.content_hash(b"abc", algorithm="rc4")

    def test_mime_detect(self):
        from module_ai.functions import builtin

        assert builtin.mime_detect("报告.PDF".lower()) == "application/pdf"
        assert builtin.mime_detect("a.docx") == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert builtin.mime_detect("x.unknownext") == "application/octet-stream"

    def test_regex_extract(self):
        from module_ai.functions import builtin

        assert builtin.regex_extract("邮箱 a@b.com 和 c@d.org", r"[\w.]+@[\w.]+") == ["a@b.com", "c@d.org"]
        assert builtin.regex_extract("无匹配", r"\d+") == []

    def test_purity_no_io(self, monkeypatch):
        """纯函数约定: 断言内置函数不触碰 网络/文件(运行期零 I/O, CA-06 静态路线)"""
        from module_ai.functions import builtin

        def _forbidden(*args, **kwargs):
            raise AssertionError("static_func 触碰了 I/O(违反纯函数约定)")

        monkeypatch.setattr("builtins.open", _forbidden)
        monkeypatch.setattr("socket.socket", _forbidden, raising=False)
        builtin.content_hash(b"x")
        builtin.mime_detect("a.pdf")
        builtin.regex_extract("abc", r"b")


class TestCapabilityResolution:
    """capability_registry.resolve 双源解析"""

    async def test_static_func_resolved_first(self):
        from module_ai.service.capability_registry import resolve

        r = await resolve("content_hash", user_id=None)
        assert r.kind == "static_func" and r.available

    async def test_feature_provider(self):
        from module_ai.service.capability_registry import (
            _FEATURE_PROVIDERS,
            register_feature_provider,
            resolve,
        )

        async def _probe(suffix: str, user_id) -> bool:
            return suffix == "bm25"

        register_feature_provider("store", _probe)
        try:
            r = await resolve("store:bm25", user_id=None)
            assert r.kind == "feature" and r.available
            r2 = await resolve("store:unknown", user_id=None)
            assert not r2.available
        finally:
            _FEATURE_PROVIDERS.pop("store", None)

    async def test_unknown_capability_unavailable(self):
        from module_ai.service.capability_registry import resolve

        r = await resolve("definitely_not_a_capability", user_id=None)
        assert r.kind == "none" and not r.available
