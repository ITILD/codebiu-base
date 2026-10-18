"""OCR 工具包: 在线(外部服务)文字识别引擎

模型能力全部通过外部服务接入, 按 server_type/extra.protocol 分派:
    - dashscope: 阿里云百炼 qwen-vl-ocr 系在线模型(整图文本识别, 语言自动检测)
    - online: PaddleOCR 官方云 API(PaddleOCR-VL/PP-OCR 系, 异步 jobs 协议;
              extra.protocol=dashscope 时仍走百炼方案)
"""
from module_ai.utils.ocr.dashscope import DashscopeOCR
from module_ai.utils.ocr.paddle_online import PaddleOCROnline

__all__ = ["DashscopeOCR", "PaddleOCROnline"]
