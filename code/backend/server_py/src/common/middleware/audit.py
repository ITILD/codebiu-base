"""操作审计中间件(REQ-009): 写操作与登录登出全量记录, 批量缓冲异步落库

分层约定: 本文件属 common 层, 不直接依赖任何 module_*;
落库 sink 由 module_main 在启动钩子中注册(见 module_main/config/server.py)。

记录范围:
- 仅写方法(POST/PUT/DELETE/PATCH); 读操作不记
- 高频/调试端点跳过(docs/openapi/token 刷新与 OAuth2 调试端点)
- 请求体仅采集 json/表单且 ≤8KB, 敏感字段(密码/令牌/密钥)递归脱敏
- 任何审计环节异常只告警, 绝不影响业务请求
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# 仅记录写方法(登录/登出均为 POST, 天然覆盖)
WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
# 精确跳过路径(文档/调试)
SKIP_PATH_EXACT = {"/docs", "/openapi.json", "/redoc", "/favicon.ico"}
# 后缀跳过(高频令牌端点, 非数据写操作)
SKIP_PATH_SUFFIX = ("/authorization/auth/refresh", "/authorization/auth/token")
# 敏感字段关键字(键名小写包含即脱敏)
SENSITIVE_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
)
MASK = "***"
# 请求体采集上限(字节): 文件上传/大报文只记占位
MAX_BODY_BYTES = 8 * 1024
# 摘要落库截断长度
DIGEST_MAX = 2000


def mask_sensitive(value: Any) -> Any:
    """递归脱敏: dict 按键名匹配敏感词替换为 ***, list 逐项递归"""
    if isinstance(value, dict):
        return {
            k: (MASK if any(s in k.lower() for s in SENSITIVE_KEYS) else mask_sensitive(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(v) for v in value]
    return value


class AuditRecorder:
    """缓冲式异步落库器: 攒满一批或超时即后台写入, 失败仅告警"""

    BATCH = 20
    DELAY = 3.0

    def __init__(self) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._sink: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None
        self._task: asyncio.Task | None = None

    def set_sink(self, sink: Callable[[list[dict[str, Any]]], Awaitable[None]]) -> None:
        """注册落库入口(module_main 启动钩子调用)"""
        self._sink = sink

    def record(self, entry: dict[str, Any]) -> None:
        """入队一条审计记录(满批立即调度刷新, 否则延迟刷新兜底)"""
        self._buffer.append(entry)
        if len(self._buffer) >= self.BATCH:
            self.flush()
        elif self._task is None or self._task.done():
            self._task = asyncio.create_task(self._delayed_flush())

    def flush(self) -> None:
        """调度后台落库(非阻塞, 不等待)"""
        entries, self._buffer = self._buffer, []
        if not entries:
            return
        if self._sink is None:
            logger.warning(f"audit sink 未注册, 丢弃 {len(entries)} 条审计记录")
            return
        asyncio.create_task(self._write(entries))

    async def flush_now(self) -> None:
        """立即落库并等待完成(测试与服务关停使用)"""
        entries, self._buffer = self._buffer, []
        if entries:
            await self._write(entries)

    async def _delayed_flush(self) -> None:
        await asyncio.sleep(self.DELAY)
        self.flush()

    async def _write(self, entries: list[dict[str, Any]]) -> None:
        try:
            await self._sink(entries)  # type: ignore[misc]
        except Exception as e:
            logger.warning(f"审计落库失败(丢弃 {len(entries)} 条): {e}")


# 全局单例(中间件写入/启动钩子注册 sink/关停 flush_now)
audit_recorder = AuditRecorder()


class AuditMiddleware(BaseHTTPMiddleware):
    """操作审计 HTTP 中间件"""

    async def dispatch(self, request: Request, call_next):
        from common.config.dynamic import get_settings
        from common.config.dynamic.schemas import AuditSettings

        path = request.url.path
        if (
            request.method not in WRITE_METHODS
            or path in SKIP_PATH_EXACT
            or path.endswith(SKIP_PATH_SUFFIX)
        ):
            return await call_next(request)
        try:
            enabled = (await get_settings(AuditSettings)).enabled
        except Exception:
            enabled = True  # 配置读取失败按启用处理(宁多记不漏记)
        if not enabled:
            return await call_next(request)

        digest, parsed_body = await self._capture_body(request)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            self._record(request, path, digest, parsed_body, 500, start)
            raise
        self._record(request, path, digest, parsed_body, response.status_code, start)
        return response

    async def _capture_body(self, request: Request) -> tuple[str | None, dict | None]:
        """采集请求体摘要(重注入 body 保证下游可读), 返回 (摘要, 解析后 dict)"""
        content_type = request.headers.get("content-type", "")
        if not any(
            t in content_type
            for t in ("application/json", "application/x-www-form-urlencoded")
        ):
            return "(非结构化请求体, 未采集)", None
        length = request.headers.get("content-length")
        if length and int(length) > MAX_BODY_BYTES:
            return "(请求体过大, 未采集)", None
        try:
            body = await request.body()
            # 重注入接收通道(BaseHTTPMiddleware 下游共享同一 Request)
            async def receive() -> dict:
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
            if not body:
                return None, None
            if "json" in content_type:
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    parsed = {"_root": parsed}
            else:
                qs = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
                parsed = {k: (v[0] if len(v) == 1 else v) for k, v in qs.items()}
            masked = mask_sensitive(parsed)
            digest = json.dumps(masked, ensure_ascii=False)
            return digest[:DIGEST_MAX], parsed
        except Exception as e:
            return f"(请求体解析失败: {e})", None

    def _record(
        self,
        request: Request,
        path: str,
        digest: str | None,
        parsed_body: dict | None,
        status_code: int,
        start: float,
    ) -> None:
        """构建审计条目入队; 任何异常只告警"""
        try:
            forwarded = request.headers.get("x-forwarded-for", "")
            ip = forwarded.split(",")[0].strip() or (
                request.client.host if request.client else ""
            )
            # 登录请求无鉴权依赖, 用户名从表单体提取; 其余请求取鉴权依赖写入的 state
            username = None
            if path.endswith("/auth/login") and isinstance(parsed_body, dict):
                username = str(parsed_body.get("username") or "") or None
            entry = {
                "user_id": getattr(request.state, "user_id", None),
                "username": username,
                "method": request.method,
                "path": path,
                "params_digest": digest,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "ip": ip or None,
                "user_agent": request.headers.get("user-agent"),
            }
            audit_recorder.record(entry)
        except Exception as e:
            logger.warning(f"审计记录构建失败(不影响业务): {e}")
