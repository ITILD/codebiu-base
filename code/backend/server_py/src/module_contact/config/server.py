"""联系触达模块 子应用装配: 通知中心路由挂载与字典种子注册(REQ-011)

module_contact 由验证码"库模式"升级为常规模块:
- 验证码能力保持原状(module_authorization 经服务导入调用, 无路由)
- 通知中心新增 /contact/notifications* 自助接口(登录即可)
"""

import logging

from common.config.server import app
from common.utils.fastapi_ex.exceptions import BizFastAPI

logger = logging.getLogger(__name__)

# 模块子应用(挂载到主应用 /contact 路径下)
module_app = BizFastAPI()
app.mount("/contact", module_app)

# 导入字典种子声明(通知类型字典注册到字典中心, 幂等)
from module_contact.config import dict_seed as contact_dict_seed  # noqa: F401, E402

logger.debug("ok...server module_contact服务配置")
