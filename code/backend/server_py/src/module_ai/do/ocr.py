"""AI 模型接入模块 ocr 表模型与请求/响应体定义"""


from pydantic import BaseModel
class Base64File(BaseModel):
    image_base64: str
    lang: str
    inpaint:bool = False