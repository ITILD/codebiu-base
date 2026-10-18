"""系统主模块 status 表模型与请求/响应体定义"""

from pydantic import BaseModel
from sqlmodel import Field, SQLModel
from uuid import uuid4
from datetime import datetime

from common.utils.sys.do.status import HardwareStatus, NetworkStatus

# 服务器状态
class StatusServer(BaseModel):
    hardware: HardwareStatus | None = None
    network: list[NetworkStatus] | None = None
    
    
    
