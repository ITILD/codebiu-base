"""ops_agent(static_agent): worker 自愈编排(REQ-019 §6.2 运维能力 Agent 化)

「心跳缺失 → 重启 → 校验 → 仍缺副本 → 扩容」用声明式 steps + skip_if 表达
(决策 rule 固定步骤, 模型不参与); 编排只调 Skill 句柄(sys.container_*), 不碰 docker。

执行流程(fan_out=hosts, 每台宿主机独立走一遍):
    1. probe    sys.container_list      探测容器状态(产出 running/abnormal_count/unhealthy_id)
    2. restart  sys.container_restart   skip_if: probe.abnormal_count == 0(无异常即跳过);
                                        consume container_id ← probe.unhealthy_id
    3. verify   sys.container_list      重启后校验(仍依赖 probe 产物, 重启被跳过不阻断)
    4. scale_up sys.container_scale_up  skip_if: verify.running >= item.expected_replicas
                                        (副本已达标即跳过; 否则差值克隆扩容)

输入(job input):
    {"hosts": [{"host_id": "...", "expected_replicas": 2}, ...]}
"""

from module_agent.agents.manifest import AgentJobManifest, AgentStepDef, register_agent_job

register_agent_job(
    AgentJobManifest(
        namespace="sys",
        key="ops_worker_heal",
        name="Worker 自愈",
        description=(
            "worker 宿主机自愈编排: 探测容器状态 → 重启异常容器 → 校验 → "
            "副本数仍不达标则克隆扩容。全步骤 rule 决策, 原语经 sys.container_* Skill "
            "(skill_invocation 全程可追溯)。"
        ),
        agent_kind="job",
        decision_mode="rule",
        steps=[
            AgentStepDef(
                id="probe",
                skill="sys.container_list",
                item_key="host_id",
            ),
            AgentStepDef(
                id="restart",
                skill="sys.container_restart",
                depends_on=["probe"],
                item_key="host_id",
                skip_if="probe.abnormal_count == 0",
                consume={"container_id": "probe.unhealthy_id"},
            ),
            AgentStepDef(
                id="verify",
                skill="sys.container_list",
                depends_on=["probe"],
                item_key="host_id",
            ),
            AgentStepDef(
                id="scale_up",
                skill="sys.container_scale_up",
                depends_on=["verify"],
                item_key="host_id",
                skip_if="verify.running >= item.expected_replicas",
            ),
        ],
        runtime_policy={"priority_class": "interactive", "max_parallel": 4},
    )
)
