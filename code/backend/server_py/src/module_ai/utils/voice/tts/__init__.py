"""TTS 语音合成子包: 在线(远程API)引擎

协议/框架细节按 extra 分派:
- extra.protocol=dashscope: 百炼 CosyVoice 流式 WebSocket / 非流式 HTTP
- extra.protocol=openai: OpenAI 兼容 /v1/audio/speech
"""
from .dashscope import DashscopeTTS
from .online import OnlineTTS

__all__ = ["DashscopeTTS", "OnlineTTS"]
