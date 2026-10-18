"""module_ai 公共工具包

按模型大类划分工具子包(模型能力全部通过外部服务接入, 基础框架不内置本地推理):
    - llm:    大语言模型(类型枚举/配置/实例工厂/token 工具/重排/文本拆分等)
    - ocr:    光学字符识别(dashscope 在线引擎)
    - voice:  语音(asr/tts 在线引擎, 协议按 extra.protocol 分派)
"""
