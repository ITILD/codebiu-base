"""voice 语音工具包: asr/tts 在线引擎包(模型能力全部通过外部服务接入)

子包职责(每种任务均以 interface.py 抽象接口为统一契约):
    - asr:     语音识别 - DashscopeASR / OnlineASR(在线 API 方案, 协议按 extra.protocol 分派)
    - tts:     语音合成 - DashscopeTTS / OnlineTTS(在线 API 方案, 协议按 extra.protocol 分派)
    - audio:   音频加载/重采样/PCM 转换公共工具
"""
from module_ai.utils.voice.asr import OnlineASR
from module_ai.utils.voice.interface import ASREngine, TTSEngine
from module_ai.utils.voice.tts import OnlineTTS

__all__ = ["ASREngine", "TTSEngine", "OnlineASR", "OnlineTTS"]
