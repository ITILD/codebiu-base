"""智能体模块权限声明(REQ-013)

agent 域节点:
- agent:manage 助手管理(后台管理页, 默认不授予, 管理员在角色管理中分配)
- 对话能力沿用 rag:chat:write(智能体对话与知识库问答同属"AI 助手"入口)
"""

from module_authorization.config.registry import (
    ModulePermissionDefine,
    PermNode,
    permission_registry,
)

AGENT_DEFINE = ModulePermissionDefine(
    module="agent",
    name="智能体",
    icon="MagicStick",
    order_num=35,
    description="AI 助手与智能体框架: 自建助手/Skill 注册表/工具调用循环",
    nodes=[
        PermNode(
            name="助手管理",
            code="agent:manage",
            menu_type="C",
            path="/agent/manage",
            order_num=1,
            children=[
                PermNode(name="查询", code="agent:manage:read", menu_type="F"),
                PermNode(name="创建", code="agent:manage:create", menu_type="F"),
                PermNode(name="操作", code="agent:manage:update", menu_type="F"),
                PermNode(name="删除", code="agent:manage:delete", menu_type="F"),
            ],
        ),
    ],
    # 自建助手登录即可, 管理节点默认不授予
    default_policies=[],
)

# 注册到权限中心(app 导入本模块 config 时生效)
permission_registry.register(AGENT_DEFINE)
