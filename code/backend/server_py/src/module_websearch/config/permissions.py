"""
module_websearch 权限声明(网页搜索模块自治声明本模块涉及的权限)

域(dom)说明:
    "websearch"  网页搜索模块域(引擎列表/搜索接口/RAG 联网检索)

节点说明: 本模块无独立菜单页(搜索能力内嵌于知识库会话页, 接口供前端按需调用),
故资源节点 visible=False 仅用于权限树展示与接口鉴权。

修改本模块权限只需编辑本文件,重启后自动幂等同步 casbin 与权限表。
"""
from module_authorization.config.registry import (
    ModulePermissionDefine,
    PermNode,
    permission_registry,
)

WEBSEARCH_DEFINE = ModulePermissionDefine(
    module="websearch",
    name="网页搜索",
    icon="Search",
    order_num=40,
    description="duckduckgo/tavily/firecrawl 网页搜索与 RAG 联网检索",
    nodes=[
        PermNode(
            name="网页搜索",
            code="websearch:search",
            menu_type="C",
            visible=False,  # 无独立菜单页: 能力内嵌于知识库会话页
            order_num=1,
            children=[
                PermNode(name="查询", code="websearch:search:read", menu_type="F"),
            ],
        ),
    ],
    # 默认新模块不带权限(default_policies=[]):
    # 普通用户需管理员在 角色管理→分配权限 中按需勾选本模块权限码
    default_policies=[],
)

# 注册到权限中心(app 导入本模块 config 时生效)
permission_registry.register(WEBSEARCH_DEFINE)
