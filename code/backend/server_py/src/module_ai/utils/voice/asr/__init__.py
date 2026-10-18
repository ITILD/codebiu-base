"""ASR 语音识别子包: 在线(远程API)引擎

协议/框架细节按 extra 分派:
- extra.protocol=dashscope: 百炼 qwen3-asr-flash(整段) / paraformer-realtime·gummy(实时 WS 流式)
- extra.protocol=openai: OpenAI 兼容 /v1/audio/transcriptions(本地 vllm 等发布端)
"""
from .dashscope import DashscopeASR
from .online import OnlineASR

__all__ = ["DashscopeASR", "OnlineASR"]
