"""网页搜索模块 子应用装配: 路由挂载与模块级初始化"""

from common.config.server import app
from common.utils.fastapi_ex.exceptions import BizFastAPI
import logging

# 导入即注册本模块权限声明到权限中心(websearch 域)
from module_websearch.config import permissions as websearch_permissions  # noqa: F401

logger = logging.getLogger(__name__)

module_app = BizFastAPI()

app.mount("/websearch", module_app)

logger.debug("module_websearch服务配置完成")
