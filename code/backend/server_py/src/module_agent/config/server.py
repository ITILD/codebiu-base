"""智能体模块 子应用装配: 路由挂载 / 权限注册 / 内置双 Agent 种子(REQ-013)

智能体对话复用 rag 会话表(conversation.agent_id 标记), 本模块仅挂载:
- /agent/agents*    助手 CRUD(自建登录即可)
- /agent/skills     技能注册表清单
- /agent/chat/...   智能体流式对话(SSE, rag:chat:write 权限)
"""

import logging

from common.config.lifespan import register_init_hook
from common.config.server import app
from common.utils.fastapi_ex.exceptions import BizFastAPI

# 导入即注册本模块权限声明到权限中心(agent 域)
from module_agent.config import permissions as agent_permissions  # noqa: F401

logger = logging.getLogger(__name__)

# 模块子应用(挂载到主应用 /agent 路径下)
module_app = BizFastAPI()
app.mount("/agent", module_app)


@register_init_hook
async def seed_builtin_agents():
    """建表后幂等播种内置双 Agent(通用助手/全能智能体)"""
    from module_agent.service.agent import AgentService

    try:
        await AgentService().seed_builtin_agents()
    except Exception as e:
        logger.warning(f"内置智能体播种失败(下次启动重试): {e}")


logger.debug("ok...server module_agent服务配置")
