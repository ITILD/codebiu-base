"""Agent 编排层(REQ-018): 内置 job Agent 声明与注册表

- Agent 是编排单元, 本身不实现业务能力; static_agent(decision_mode=rule)的
  步骤/分支/依赖全部显式声明(禁模型自由选择, CA-07)
- job 编排能力边界(最终设计): 线性 steps + fan_out + depends_on + 批内条件
  when/skip_if; 动态依赖/循环/子工作流/Agent 嵌套不引入(W-1 禁止 Agent 调 Agent)
"""

from module_agent.agents.manifest import (  # noqa: F401 (重导出)
    AGENT_JOBS,
    AgentJobManifest,
    AgentStepDef,
    get_agent_job,
    list_agent_jobs,
    register_agent_job,
)
from module_agent.agents import kb_ingest  # noqa: F401 (导入即注册)
