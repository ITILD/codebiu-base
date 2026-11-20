"""容器运维原语 Skill(static_skill, REQ-019 §6.2 运维能力 Agent 化)

把游离在三层之外的 app_agent.py(已更名 app_host_probe.py) docker 原语收编为 5 个 static_skill:
    sys.container_list / container_start / container_stop / container_restart / container_scale_up

分层契约(设计 §6.2):
- Skill 层不直接碰 docker.sock: 全部经 HTTP 调宿主机探针(host_probe, Bearer 认证),
  复用 worker_host._agent_request 单点客户端(探针契约单一定义, 主服务不重复手写);
- 探针只暴露最小原语集并按 compose 服务名过滤, 优雅摘除语义(stop=SIGTERM warm
  shutdown, acks_late 重投)写在本文件的 side_effects 与注释里(不再只在脚本注释);
- 所有原语调用经 SkillRuntime → skill_invocation 可追溯(谁在什么时候动了容器);
- 幂等键 = host + 目标容器标识 + 动作(设计 §6.2);
- 缩容安全流程(backlog 判定/稳定窗口/逐个摘除)仍属编排语义, 在 WorkerHostService,
  不下沉到 Skill(原语保持最小)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    RetrySpec,
    SkillManifest,
    SkillNature,
)
from module_agent.skills.registry import register_skill

if TYPE_CHECKING:  # 仅类型注解用, 运行期不导入(避免注册链循环)
    from module_agent.service.skill_runtime import (
        CapabilityResolution,
        ProgressFn,
        SkillContext,
    )

# agent 侧管理的 compose 服务名(与 worker_host.WORKER_SERVICE 一致)
_DEFAULT_SERVICE = "task_worker"
# stop/restart 默认优雅等待(秒, 建议 >= 最长任务时长; 与 worker_host._DEFAULT_GRACE 对齐)
_DEFAULT_GRACE = 600


def _register(
    key: str,
    name: str,
    description: str,
    properties: dict,
    required: list[str],
    side_effects: str,
    inline_timeout_s: int,
    idempotency_keys: list[str],
    output_properties: dict,
) -> None:
    """注册一个 container_* Skill(公共契约收敛: 全部 static/inline/零重试)"""
    register_skill(
        SkillManifest(
            namespace="sys",
            key=key,
            name=name,
            description=description,
            category="ops",
            nature=SkillNature.STATIC.value,
            impl_ref=f"module_task.skills.container_ops:{key.replace('sys.container_', '')}_run",
            input_schema={
                "type": "object",
                "required": required,
                "properties": properties,
            },
            output_schema={"type": "object", "properties": output_properties, "required": []},
            execution=ExecutionSpec(modes=["inline"], inline_timeout_s=inline_timeout_s),
            idempotency=IdempotencySpec(keys=idempotency_keys),
            retry=RetrySpec(max=0),  # 运维动作不自动重试(重复 stop/克隆有副作用, 失败交编排决策)
            side_effects=side_effects,
            agent_callable=True,
        )
    )


# ── 5 个原语契约(sys 命名空间, 设计 §6.2) ──────────────────────────
_register(
    "container_list", "容器列表",
    "列出指定宿主机上 compose 服务的容器(全部状态, 含 hostname/state/启动时间), 用于运维探测与自愈判定。",
    {
        "host_id": {"type": "string", "description": "宿主机ID(sys_worker_host 注册表)"},
        "service": {"type": "string", "default": _DEFAULT_SERVICE, "description": "compose 服务名"},
    },
    ["host_id"],
    side_effects="read",
    inline_timeout_s=30,
    idempotency_keys=["host_id", "service"],
    output_properties={
        "containers": {"type": "array", "items": {"type": "object"}},
        "total": {"type": "integer"},
        "running": {"type": "integer"},
        "abnormal_count": {"type": "integer"},
        "unhealthy_id": {"type": ["string", "null"]},
    },
)
_register(
    "container_start", "启动容器",
    "启动宿主机上已停止的容器。",
    {
        "host_id": {"type": "string", "description": "宿主机ID"},
        "container_id": {"type": "string", "description": "目标容器ID(短ID或完整ID)"},
    },
    ["host_id", "container_id"],
    side_effects="write",
    inline_timeout_s=60,
    idempotency_keys=["host_id", "container_id"],
    output_properties={"result": {"type": "object"}},
)
_register(
    "container_stop", "优雅停止容器",
    "停止容器(SIGTERM=warm shutdown, 等在途任务完成, 超时强杀后消息由 acks_late 重投); "
    "remove=true 时停止后移除(缩容语义); 人工停止不受 restart 策略自动拉起。",
    {
        "host_id": {"type": "string", "description": "宿主机ID"},
        "container_id": {"type": "string", "description": "目标容器ID"},
        "grace": {"type": "integer", "default": _DEFAULT_GRACE, "description": "优雅等待秒数"},
        "remove": {"type": "boolean", "default": False, "description": "停止后移除(缩容用)"},
    },
    ["host_id", "container_id"],
    side_effects="write",
    inline_timeout_s=900,
    idempotency_keys=["host_id", "container_id"],
    output_properties={"result": {"type": "object"}},
)
_register(
    "container_restart", "重启容器",
    "重启容器(滚动重启语义: grace 秒内等优雅退出, 超时强杀; restart 策略语义不变)。",
    {
        "host_id": {"type": "string", "description": "宿主机ID"},
        "container_id": {"type": "string", "description": "目标容器ID"},
        "grace": {"type": "integer", "default": 60, "description": "优雅等待秒数"},
    },
    ["host_id", "container_id"],
    side_effects="write",
    inline_timeout_s=180,
    idempotency_keys=["host_id", "container_id"],
    output_properties={"result": {"type": "object"}},
)
_register(
    "container_scale_up", "容器扩容",
    "克隆扩容: 以最新容器为模板克隆至期望副本数(无风险, 同步完成); "
    "传 expected_replicas 时自动计算需新增数量(当前运行数不足才克隆)。",
    {
        "host_id": {"type": "string", "description": "宿主机ID"},
        "service": {"type": "string", "default": _DEFAULT_SERVICE, "description": "compose 服务名"},
        "count": {"type": "integer", "default": 1, "minimum": 1, "description": "新增容器数(count 与 expected_replicas 二选一)"},
        "expected_replicas": {"type": "integer", "minimum": 0, "description": "期望运行副本数(自动差值计算)"},
    },
    ["host_id"],
    side_effects="write",
    inline_timeout_s=180,
    idempotency_keys=["host_id", "service", "count"],
    output_properties={
        "created": {"type": "array", "items": {"type": "string"}},
        "count": {"type": "integer"},
        "running": {"type": "integer"},
    },
)


# ── 公共执行辅助 ──────────────────────────────────────────────


async def _probe_call(
    host_id: str, method: str, path: str, *,
    json_body: dict | None = None, params: dict | None = None,
    timeout: float | None = None,
) -> dict | list:
    """经 sys_worker_host 注册表解析宿主机并调探针(探针契约单点: worker_host._agent_request)"""
    from module_task.dao.task import TaskQueueDao
    from module_task.service.worker_host import _agent_request

    host = await TaskQueueDao().get_worker_host(host_id)
    if host is None:
        from common.utils.fastapi_ex.exceptions import NotFoundError

        raise NotFoundError(f"未找到ID为 {host_id} 的宿主机")
    if not host.enabled:
        from common.utils.fastapi_ex.exceptions import BusinessError

        raise BusinessError(f"主机 {host.host_name} 已停用")
    return await _agent_request(
        host, method, path, json_body=json_body, params=params,
        timeout=timeout or 5.0,
    )


# ── Skill 实现(签名统一 run(input, ctx, caps, progress), CA-04) ──────────


async def list_run(skill_input: dict, ctx: "SkillContext", caps: "CapabilityResolution", progress: "ProgressFn") -> dict:
    """容器列表 + 自愈判定摘要(异常容器ID取首个, 供编排 consume 传递)"""
    await progress(30, "探测宿主机容器")
    service = str(skill_input.get("service") or _DEFAULT_SERVICE)
    containers = await _probe_call(
        str(skill_input["host_id"]), "GET", "/containers", params={"service": service}
    )
    containers = containers or []
    running = [c for c in containers if c.get("state") == "running"]
    abnormal = [c for c in containers if c.get("state") not in ("running", "removing")]
    await progress(100, "探测完成")
    return {
        "containers": containers,
        "total": len(containers),
        "running": len(running),
        "abnormal_count": len(abnormal),
        # 编排 consume 用: 首个异常容器(自愈重启目标)
        "unhealthy_id": abnormal[0].get("id") if abnormal else None,
    }


async def start_run(skill_input: dict, ctx: "SkillContext", caps: "CapabilityResolution", progress: "ProgressFn") -> dict:
    """启动已停止容器"""
    await progress(30, "启动容器")
    result = await _probe_call(
        str(skill_input["host_id"]), "POST",
        f"/containers/{skill_input['container_id']}/start",
        timeout=60.0,
    )
    await progress(100, "已启动")
    return {"result": result}


async def stop_run(skill_input: dict, ctx: "SkillContext", caps: "CapabilityResolution", progress: "ProgressFn") -> dict:
    """优雅停止(SIGTERM=warm shutdown, 超时强杀消息重投), 可选移除(缩容)"""
    grace = max(1, int(skill_input.get("grace") or _DEFAULT_GRACE))
    await progress(30, f"优雅停止中(最多等 {grace}s)")
    result = await _probe_call(
        str(skill_input["host_id"]), "POST",
        f"/containers/{skill_input['container_id']}/stop",
        json_body={"grace": grace, "remove": bool(skill_input.get("remove", False))},
        timeout=grace + 120.0,
    )
    await progress(100, "已停止")
    return {"result": result}


async def restart_run(skill_input: dict, ctx: "SkillContext", caps: "CapabilityResolution", progress: "ProgressFn") -> dict:
    """重启容器(滚动重启)"""
    grace = max(1, int(skill_input.get("grace") or 60))
    await progress(30, f"重启容器(优雅等待 {grace}s)")
    result = await _probe_call(
        str(skill_input["host_id"]), "POST",
        f"/containers/{skill_input['container_id']}/restart",
        json_body={"grace": grace},
        timeout=grace + 120.0,
    )
    await progress(100, "已重启")
    return {"result": result}


async def scale_up_run(skill_input: dict, ctx: "SkillContext", caps: "CapabilityResolution", progress: "ProgressFn") -> dict:
    """克隆扩容至期望副本数(显式 count 优先; expected_replicas 自动差值)"""
    service = str(skill_input.get("service") or _DEFAULT_SERVICE)
    count = skill_input.get("count")
    expected = skill_input.get("expected_replicas")
    if count:
        count = max(1, int(count))
    else:
        await progress(20, "探测当前副本数")
        listing = await list_run({"host_id": skill_input["host_id"], "service": service}, ctx, caps, progress)
        if expected is None:
            from common.utils.fastapi_ex.exceptions import BusinessError

            raise BusinessError("count 与 expected_replicas 至少提供一个")
        count = max(0, int(expected) - int(listing["running"]))
        if count == 0:
            await progress(100, "副本数已达标, 无需扩容")
            return {"created": [], "count": 0, "running": listing["running"]}
    await progress(50, f"克隆扩容 +{count}")
    result = await _probe_call(
        str(skill_input["host_id"]), "POST", "/scale-up",
        json_body={"service": service, "count": count},
        timeout=180.0,
    )
    await progress(100, "扩容完成")
    return {"created": result.get("created") or [], "count": count}
