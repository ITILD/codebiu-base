"""智能体模块服务器装配(REQ-013/REQ-018)

- 装配模式与既有模块一致: 先定义子应用并挂载, controller 自行 import
  module_app 挂载路由(本文件只触发导入, 不引用 controller 符号, 避免循环导入)
- 注册 init 钩子: 启动时同步内置 Skill 资产(W-8 代码为源只读同步)
"""

from common.config.lifespan import register_init_hook
from common.config.server import app
from common.utils.fastapi_ex.exceptions import BizFastAPI

module_app = BizFastAPI()

app.mount("/agent", module_app)

# 触发 controller 挂载与权限声明(必须在 module_app 定义之后导入)
from module_agent.config import permissions  # noqa: F401, E402 (导入即注册权限声明)
from module_agent.controller import agent as agent_controller  # noqa: F401, E402 (自挂载)
from module_agent.controller import skill as skill_controller  # noqa: F401, E402 (自挂载)


@register_init_hook
async def _sync_skill_assets() -> None:
    """建表后同步内置 Skill 清单到 ai_skill/ai_skill_version(幂等, 失败仅告警);
    恢复已发布的自定义 prompt Skill 注册(REQ-018 批次 2);
    并幂等播种内置双 Agent(存在则按代码刷新名称/描述/技能名单, REQ-018 键升级)"""
    from module_agent.service.agent import AgentService

    try:
        from module_agent.service.skill_asset import sync_builtin_skills

        await sync_builtin_skills()
    except Exception as e:  # 同步失败不阻断启动(下次启动重试)
        import logging

        logging.getLogger(__name__).warning("Skill 资产同步失败(忽略): %s", e)
    try:
        from module_agent.service.prompt_skill import restore_custom_prompt_skills

        await restore_custom_prompt_skills()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("自定义 Skill 恢复失败(忽略): %s", e)
    try:
        from module_agent.service.skill_hub import restore_skill_hub_packages

        await restore_skill_hub_packages()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Skill Hub 包恢复失败(忽略): %s", e)
    try:
        from module_agent.service.mcp_adapter import restore_mcp_servers

        await restore_mcp_servers()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("MCP tools 恢复失败(忽略): %s", e)
    await AgentService().seed_builtin_agents()
