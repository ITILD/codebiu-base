"""文档解析模块 子应用装配: 路由挂载与模块级初始化"""

from common.config.server import app
# lib
from common.utils.fastapi_ex.exceptions import BizFastAPI
import logging

logger = logging.getLogger(__name__)

module_app = BizFastAPI()

app.mount("/office", module_app)

logger.debug("module_office服务配置完成")
