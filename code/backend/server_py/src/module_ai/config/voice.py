"""语音服务配置(在线 ASR/TTS 参数)"""

from common.config.index import conf
import logging

logger = logging.getLogger(__name__)

# 默认采样率
VOICE_DEFAULT_SAMPLE_RATE = 22050

# 从 config.yaml 读取 voice 配置(可选，缺失时使用默认值)
try:
    conf_voice = conf.voice
    if conf_voice is None:
        conf_voice = {}
except Exception:
    conf_voice = {}

# ---------- Online 引擎配置(远程API或本地vllm发布) ----------
conf_voice_online = conf_voice.get("online", {}) if conf_voice else {}

# DashScope WebSocket 推理端点(实时 ASR / 流式 TTS 共用)
VOICE_ONLINE_WS_URL: str = conf_voice_online.get(
    "ws_url", "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"
)
# 命中实时系列的模型名前缀(走真 WS 流式), 其余在线模型走伪流式(缓冲切片调同步接口)
VOICE_ONLINE_REALTIME_ASR_MODELS: list[str] = list(
    conf_voice_online.get("realtime_asr_models", ["paraformer-realtime", "gummy"])
)
# 伪流式切片时长(秒): 缓冲达到该时长即提交后台识别
VOICE_ONLINE_PSEUDO_CHUNK_SECONDS: float = float(conf_voice_online.get("pseudo_chunk_seconds", 2.5))

logger.debug("ok...voice 语音配置加载完成")
