"""MCP adapter: MCP server tools 反射注册为 mcp_tool Skill(REQ-018 批次 3, W-15)

设计落点(04 设计文档 §3.5): MCP tools 经 adapter 反射进统一注册表——
JSON Schema → input_schema, 实现 = MCP client 调用, 幂等 none(MCP 无幂等语义),
execution 默认 inline; 命名空间 mcp.{server}.{tool}。resources 归知识资产管理、
prompts 可按需包装, 本 adapter 只反射 tools(约定)。

零依赖实现: stdio transport 的 MCP 即 newline-delimited JSON-RPC 2.0,
本模块自实现最小客户端(initialize 握手 / tools/list / tools/call),
不引入 mcp 官方 SDK(依赖白名单零新增); SSE transport 暂不支持(后续按需)。
连接策略: 每次 Skill 调用新建短连接(spawn → 握手 → call → 关闭),
stdio server 启动轻量; 常驻连接池后置。
"""

import asyncio
import json
import logging
from typing import Any

from sqlmodel import select

from common.config.db import db_manager
from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_agent.do.skill import AiSkill, AiSkillVersion, SkillPublishStatus
from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    RetrySpec,
    SkillManifest,
)
from module_agent.skills.registry import SKILL_REGISTRY, register_skill

logger = logging.getLogger(__name__)

_MCP_PROTOCOL_VERSION = "2024-11-05"
_HANDSHAKE_TIMEOUT_S = 20
_CALL_TIMEOUT_S = 120
_MAX_TOOLS_PER_SERVER = 50


class McpError(Exception):
    """MCP 调用失败(permanent 为主: 协议/工具错误)"""


class McpStdioClient:
    """最小 MCP stdio 客户端(newline-delimited JSON-RPC 2.0)"""

    def __init__(self, command: str, args: list[str] | None = None, env: dict[str, str] | None = None):
        self._command = command
        self._args = list(args or [])
        self._env = dict(env or {})
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 1

    async def __aenter__(self) -> "McpStdioClient":
        import os

        merged_env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "TZ", "HOME")}
        merged_env.update(self._env)
        self._proc = await asyncio.create_subprocess_exec(
            self._command, *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=merged_env,
        )
        await self._request(
            "initialize",
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "codebiu-mcp-adapter", "version": "1"},
            },
            timeout=_HANDSHAKE_TIMEOUT_S,
        )
        await self._notify("notifications/initialized")
        return self

    async def __aexit__(self, *exc) -> None:
        if self._proc is not None and self._proc.returncode is None:
            self._proc.kill()
            await self._proc.wait()

    async def _send(self, payload: dict) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(payload).encode() + b"\n")
        await self._proc.stdin.drain()

    async def _read(self, timeout: float) -> dict:
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=timeout)
            if not line:
                raise McpError("MCP server 连接已断开(进程退出)")
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue  # 忽略非 JSON 噪声行
            if isinstance(message, dict) and ("id" in message or "result" in message or "error" in message):
                return message
            # 服务器主动通知/请求忽略(本客户端只做请求-响应)

    async def _request(self, method: str, params: dict | None = None, timeout: float = _CALL_TIMEOUT_S) -> Any:
        request_id = self._next_id
        self._next_id += 1
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise McpError(f"MCP 请求超时: {method}")
            response = await self._read(remaining)
            if response.get("id") != request_id:
                continue  # 乱序/其他消息
            if "error" in response and response["error"] is not None:
                error = response["error"]
                raise McpError(f"MCP 错误[{method}]: {error.get('message')}({error.get('code')})")
            return response.get("result")

    async def _notify(self, method: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": method})

    async def list_tools(self) -> list[dict]:
        result = await self._request("tools/list", timeout=_HANDSHAKE_TIMEOUT_S)
        tools = (result or {}).get("tools") or []
        if len(tools) > _MAX_TOOLS_PER_SERVER:
            raise McpError(f"工具数量超过上限 {_MAX_TOOLS_PER_SERVER}")
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            raise McpError(f"MCP 工具 {name} 返回异常结果")
        if result.get("isError"):
            texts = " ".join(
                c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict)
            )
            raise McpError(f"MCP 工具 {name} 执行失败: {texts[:500]}")
        return result


def make_mcp_runner(server_name: str, tool_name: str, command: str, args: list[str], env: dict[str, str]):
    """为 MCP tool 生成专属执行闭包(每次调用短连接, impl 契约签名)"""

    async def run(skill_input: dict, ctx, caps, progress) -> dict:
        await progress(30, f"MCP 调用 {server_name}.{tool_name}")
        async with McpStdioClient(command, args, env) as client:
            result = await client.call_tool(tool_name, dict(skill_input))
        content = result.get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        non_text = [c for c in content if isinstance(c, dict) and c.get("type") != "text"]
        output: dict[str, Any] = {"text": "\n".join(t for t in texts if t)}
        if non_text:
            output["content"] = non_text
        await progress(100, "调用完成")
        return output

    return run


def _register_mcp_tool(manifest: SkillManifest, server_cfg: dict, tool_real_name: str | None = None) -> None:
    from module_agent.service import skill_runtime as sr

    register_skill(manifest)
    # manifest.key 为规范化注册键; 调用时用 MCP 真实工具名(可能含大写/连字符)
    sr._impl_cache[manifest.impl_ref] = make_mcp_runner(
        server_cfg.get("name", ""), tool_real_name or manifest.key,
        server_cfg.get("command", ""), list(server_cfg.get("args") or []),
        dict(server_cfg.get("env") or {}),
    )


def _normalize_tool_key(raw: str) -> str:
    """MCP tool 名 → 契约 key(小写字母开头[a-z0-9_]); 冲突时后缀去重由调用方处理"""
    import re

    key = re.sub(r"[^a-z0-9_]", "_", raw.lower())
    if not key or key[0].isdigit():
        key = f"t_{key}"
    return key


def _build_tool_manifest(server: str, tool: dict, version: str) -> tuple[SkillManifest, str]:
    """JSON Schema → input_schema 反射(声明翻译, 不做语义改写); 返回 (manifest, 真实工具名)"""
    input_schema = tool.get("inputSchema")
    if not isinstance(input_schema, dict) or not input_schema.get("properties"):
        input_schema = {
            "type": "object",
            "required": ["input"],
            "properties": {"input": {"type": "string", "description": "工具输入(序列化参数)"}},
        }
    real_name = str(tool["name"])
    manifest = SkillManifest(
        namespace=f"mcp.{server}",
        key=_normalize_tool_key(real_name),
        name=str(tool.get("title") or real_name),
        description=str(tool.get("description") or f"MCP 工具 {server}.{real_name}"),
        skill_type="mcp_tool",
        nature="static",
        impl_ref=f"mcp_adapter:mcp.{server}.{_normalize_tool_key(real_name)}",
        version=version,
        input_schema=input_schema,
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        execution=ExecutionSpec(modes=["inline"], inline_timeout_s=_CALL_TIMEOUT_S),
        idempotency=IdempotencySpec(keys=[]),  # MCP 无幂等语义(§3.5)
        retry=RetrySpec(max=0),
        side_effects="external",
        agent_callable=True,
    )
    return manifest, real_name


class McpServerService:
    """MCP server 登记/反射注册/删除(同表同治 origin=external)"""

    async def register(self, req: dict, user_id: str) -> dict:
        name = str(req.get("name") or "").strip()
        command = str(req.get("command") or "").strip()
        if not name or not command or "." in name:
            raise BusinessError("必须提供 name(不含 '.')与 command")
        namespace = f"mcp.{name}"
        if await self._namespace_exists(namespace):
            raise BusinessError(f"MCP server 已登记: {namespace}")
        server_cfg = {
            "name": name, "command": command,
            "args": list(req.get("args") or []),
            "env": dict(req.get("env") or {}),
        }
        # 连接验证 + 拉取工具清单(失败即拒绝登记)
        try:
            async with McpStdioClient(command, server_cfg["args"], server_cfg["env"]) as client:
                tools = await client.list_tools()
        except Exception as e:
            raise BusinessError(f"MCP server 连接/握手失败: {e}") from e
        if not tools:
            raise BusinessError("MCP server 未暴露任何 tool")

        manifests_with_names = [_build_tool_manifest(name, t, "1") for t in tools]
        for m, _real in manifests_with_names:
            m.check_invariants()
        async with db_manager.db_rel.session_factory() as session:
            for manifest, real_name in manifests_with_names:
                snapshot = manifest.model_dump(mode="json")
                snapshot["_server"] = server_cfg
                snapshot["_tool"] = {"real_name": real_name}
                row = AiSkill(
                    key=manifest.uid, namespace=namespace, name=manifest.name,
                    description=manifest.description, category="action",
                    skill_type="mcp_tool", nature="static",
                    origin="external", origin_version="1",
                    owner_user_id=user_id,
                    current_version="1", status=SkillPublishStatus.PUBLISHED,
                )
                session.add(row)
                await session.flush()
                session.add(
                    AiSkillVersion(
                        skill_id=row.id, version="1",
                        config_hash=f"mcp:{manifest.uid}",
                        manifest_snapshot=snapshot,
                    )
                )
            await session.commit()
        for manifest, real_name in manifests_with_names:
            _register_mcp_tool(manifest, server_cfg, real_name)
        return {"namespace": namespace, "tools": [m.uid for m, _ in manifests_with_names]}

    async def list_servers(self) -> list[dict]:
        async with db_manager.db_rel.session_factory() as session:
            rows = (
                await session.exec(
                    select(AiSkill).where(
                        AiSkill.origin == "external", AiSkill.namespace.like("mcp.%")
                    )
                )
            ).all()
        servers: dict[str, dict] = {}
        for r in rows:
            server = servers.setdefault(
                r.namespace,
                {"namespace": r.namespace, "status": r.status, "owner_user_id": r.owner_user_id, "tools": []},
            )
            server["tools"].append(
                {"key": r.key, "name": r.name, "registered": SKILL_REGISTRY.get(r.key) is not None}
            )
        return sorted(servers.values(), key=lambda s: s["namespace"])

    async def remove(self, namespace: str) -> dict:
        from module_agent.service import skill_runtime as sr

        if not namespace.startswith("mcp."):
            raise BusinessError(f"非法 MCP 命名空间: {namespace}")
        async with db_manager.db_rel.session_factory() as session:
            rows = (
                await session.exec(select(AiSkill).where(AiSkill.namespace == namespace))
            ).all()
            if not rows:
                raise NotFoundError(f"MCP server 不存在: {namespace}")
            for row in rows:
                manifest = SKILL_REGISTRY.pop(row.key, None)
                if manifest is not None:
                    sr._impl_cache.pop(manifest.impl_ref, None)
                row.status = SkillPublishStatus.DEPRECATED
                row.deprecated = True
            await session.commit()
        return {"namespace": namespace, "status": "deprecated"}

    async def _namespace_exists(self, namespace: str) -> bool:
        async with db_manager.db_rel.session_factory() as session:
            row = (
                await session.exec(
                    select(AiSkill).where(AiSkill.namespace == namespace).limit(1)
                )
            ).first()
            return row is not None


async def restore_mcp_servers() -> dict:
    """启动恢复: 从 DB 重建 MCP tool 注册(不预连接, 首次调用时短连接验证)"""
    restored = 0
    async with db_manager.db_rel.session_factory() as session:
        rows = (
            await session.exec(
                select(AiSkill).where(
                    AiSkill.origin == "external",
                    AiSkill.status == SkillPublishStatus.PUBLISHED,
                    AiSkill.namespace.like("mcp.%"),
                )
            )
        ).all()
        snapshots: list[dict] = []
        for row in rows:
            latest = (
                await session.exec(
                    select(AiSkillVersion)
                    .where(AiSkillVersion.skill_id == row.id)
                    .order_by(AiSkillVersion.created_at.desc())
                    .limit(1)
                )
            ).first()
            if latest is not None:
                snapshots.append(dict(latest.manifest_snapshot or {}))
    for snapshot in snapshots:
        try:
            server_cfg = snapshot.get("_server") or {}
            real_name = (snapshot.get("_tool") or {}).get("real_name")
            manifest = SkillManifest(**{k: v for k, v in snapshot.items() if not k.startswith("_")})
            _register_mcp_tool(manifest, server_cfg, real_name)
            restored += 1
        except Exception as e:
            logger.warning("MCP tool 恢复失败: %s", e)
    logger.info("MCP tools 恢复完成: %s 个", restored)
    return {"restored": restored}
