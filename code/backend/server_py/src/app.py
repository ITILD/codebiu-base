"""服务入口: 导入即注册全部模块路由, 并提供 uvicorn 启动入口"""

from common.config import log
from common.config import net
from common.config.index import conf
from common.config.server import app

# 主模块
from module_main.controller import static as main_static, status, table, dict_type, dict_item
from module_main.controller import sys_config as main_sys_config
# # 系统管理域权限声明(通用动态配置页, main 域内节点在 module_authorization 声明)
# # 文件模块(网络文件系统: 虚拟文件树 + local/s3 存储无缝切换)
from module_file.controller import filesystem
from module_authorization.controller import token, casbin_rule, permission, role, user,auth,dept
# # 业务模块
from module_template.controller import static,template,template_ex,template_async_learn
# # AI 模块(模型配置/LLM 对话/重排/OCR/语音 ASR-TTS)
from module_ai.controller import static as ai_static,model_config,llm,rerank,voice,ocr
# # 知识库模块(项目/文档/成员/部门授权/问答)
from module_rag.controller import (
    conversation,
    project,
    project_document,
    project_document_chunk,
    project_member,
    project_dept,
    rag_chat,
    user_model,
)
# # 知识库模块: 权限声明注册保持权限表与声明一致
from module_rag.config import permissions as rag_permissions  # noqa: F401
# # 网页搜索模块(duckduckgo/tavily/firecrawl 引擎搜索 + RAG 联网检索)
from module_websearch.controller import websearch
# # 任务队列模块(本地+Celery 双引擎, RAG 文档解析任务依赖)
from module_task.controller import task
from module_task.config import permissions as task_permissions  # noqa: F401


if __name__ == "__main__":
    import asyncio
    import uvicorn
    from common.utils.sys.kill_process import find_and_kill_process

    def selector_event_loop_factory() -> asyncio.AbstractEventLoop:
        """uvicorn 自定义循环工厂(仅本启动入口使用, 故与 uvicorn.run 同处定义)

        - Windows: uvicorn>=0.36 默认工厂硬编码 ProactorEventLoop 且忽略事件循环策略设置,
          而 psycopg 异步模式(checkpointer 连接池)不支持 Proactor, 必须切 Selector
        - Linux: 默认工厂本就返回 Selector(epoll), 此工厂行为与默认一致, 无副作用
        """
        return asyncio.SelectorEventLoop()

    # 关闭之前运行的进程
    find_and_kill_process(conf.server.port)

    # dev启动服务
    uvicorn.run(
        app,
        host=conf.server.host,
        port=conf.server.port,
        loop=selector_event_loop_factory,
    )
    # uvicorn.run("src.app:app", host=conf.server.host, port=conf.server.port, reload=True)
    # 多进程
    # uvicorn.run("app:app", host=conf.server.host, port=conf.server.port,workers=1, timeout_worker_healthcheck=300)