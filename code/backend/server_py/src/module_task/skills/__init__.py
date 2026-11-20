"""module_task 领域宿主技能资产收集(REQ-019 §6.2 运维能力 Agent 化)

- 容器运维原语(sys.container_*)收编为 static_skill, 由 module_agent 技能层统一收集;
- 本包只做「导入即注册」, 实现与契约见 container_ops.py
"""

from module_task.skills import container_ops  # noqa: F401 (导入即注册)
