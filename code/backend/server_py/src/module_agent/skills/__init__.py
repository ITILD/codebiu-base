"""智能体技能包: Manifest 注册表 + 各领域宿主 Skill 收集(W-13)

- 本模块(module_agent)持有注册表(registry.py)与契约(manifest.py)及无领域宿主的
  内置技能(builtin/)
- 领域宿主 Skill(module_office/module_rag 的 skills/)在此统一收集导入,
  方向为 agent → 业务模块(与既有 builtin 包装方向一致, 无反向依赖)
"""

from module_agent.skills import builtin  # noqa: F401 (导入即注册)
from module_agent.skills import registry  # noqa: F401 (注册表视图, 兼容 from ... import SKILL_REGISTRY)
from module_office import skills as _office_skills  # noqa: F401 (领域宿主资产收集: doc_parse)
from module_rag import skills as _rag_skills  # noqa: F401 (领域宿主资产收集: doc_chunk_index + store 探测)
