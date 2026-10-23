"""全模块路由注册冒烟(REQ-010): 根直挂路由 + 各子应用挂载点各自可达

注:
- 新版 FastAPI 的 include_router 以惰性 _IncludedRouter 表示, 顶层 app.routes 无具体
  path; 根应用 /openapi.json 也不含 app.mount 挂载的子应用路径, 故分两层验证:
  ① 根 openapi 覆盖 module_main 直挂控制器; ② 逐个子应用 /openapi.json 可达且非空
- module_office 未在 app.py 接线(预存现状, 仅测试/内部服务导入时注册), 此处显式
  导入以验证其注册能力
"""

import module_office.controller.document_parse  # noqa: F401

# module_main 直挂根应用的控制器前缀
_ROOT_PREFIXES = (
    "/dict_types",     # 字典类型
    "/dict_items",     # 字典项
    "/audit_logs",     # 操作审计(REQ-009)
    "/sys-configs",    # 通用动态配置
    "/db",             # 数据库管理
    "/server-status",  # 服务状态
)

# 各模块子应用挂载点(挂载可达即代表模块装配成功)
_SUBAPPS = (
    "/authorization",
    "/file",
    "/rag",
    "/task",
    "/websearch",
    "/ai",
    "/template",
    "/office",  # 显式导入后注册
)


async def _paths_of(anon_client, base: str = "") -> set[str]:
    """拉取应用(或子应用)的 OpenAPI 路径集合"""
    resp = await anon_client.get(f"{base}/openapi.json")
    assert resp.status_code == 200, f"{base or '根应用'} openapi 不可达: {resp.status_code}"
    return set(resp.json()["paths"].keys())


async def test_main_root_routers_registered(anon_client):
    """module_main 直挂控制器的路径前缀齐全"""
    paths = await _paths_of(anon_client)
    missing = [p for p in _ROOT_PREFIXES if not any(x.startswith(p) for x in paths)]
    assert not missing, f"根直挂路由缺失: {missing}"
    assert len(paths) >= 20, f"根应用路径数量异常偏少: {len(paths)}"


async def test_module_subapps_reachable(anon_client):
    """各模块子应用挂载点 openapi 可达且路由非空"""
    for base in _SUBAPPS:
        paths = await _paths_of(anon_client, base)
        assert paths, f"子应用 {base} 无任何路由"
