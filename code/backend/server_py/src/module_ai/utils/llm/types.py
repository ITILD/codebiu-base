"""LLM 类型定义(消息/参数等)"""

from enum import Enum


class ModelServerType(str, Enum):
    """
    模型服务类型枚举: 模型能力全部通过外部服务接入(基础框架不内置本地推理)
    - chat/embeddings/rerank 类: openai/dashscope/vllm/ollama/aws
    - image(生图): openai/dashscope(百炼兼容模式, 协议与 OpenAI 一致)
    - asr/tts 类: online(远程API或本地vllm发布, 协议细节放 extra.protocol)
    - ocr 类: dashscope(阿里云在线)
    - sherpa/qwen/paddle/local 为历史方案值: ORM 存量行仍按值读取, 禁止删除(已下线, 仅作读取兼容)
    """

    OPENAI = "openai"
    DASHSCOPE = "dashscope"
    VLLM = "vllm"
    OLLAMA = "ollama"
    AWS = "aws"
    # 以下为已下线的历史方案值, 仅为兼容存量库行保留
    SHERPA = "sherpa"
    QWEN = "qwen"
    PADDLE = "paddle"
    ONLINE = "online"
    LOCAL = "local"


class ModelType(str, Enum):
    """
    模型类型枚举: chat embeddings rerank ocr asr tts image
    (vad/denoise 为历史类型值: 本地推理已下线, 仅作存量行读取兼容, 禁止删除)
    """

    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"
    OCR = "ocr"
    ASR = "asr"
    TTS = "tts"
    # 生图: 文生图(T2I)/图生图·图像编辑(I2I), 走 OpenAI 兼容 /images/generations
    IMAGE = "image"
    # 已下线的历史类型值, 仅为兼容存量库行保留
    VAD = "vad"
    DENOISE = "denoise"


def server_types_for(model_type: "ModelType | str") -> list[ModelServerType]:
    """
    按模型类型返回可用的服务方案(前端下拉/后端校验共用): 全部为外部服务接入
    - asr/tts: online(远程API或本地vllm发布, 优先 qwen3 系列)
    - ocr: dashscope(阿里云百炼)/online(PaddleOCR 官方云 API 等, 协议细节放 extra.protocol)
    - image: openai(OpenAI 兼容协议)/dashscope(百炼兼容模式同协议, 如 qwen-image 系列)
    - vad/denoise: 已下线(返回空列表, 前端不再展示)
    :param model_type: 模型类型
    :return: 服务方案列表
    """
    value = model_type.value if isinstance(model_type, ModelType) else str(model_type)
    if value in ("asr", "tts"):
        return [ModelServerType.ONLINE]
    if value == "ocr":
        return [ModelServerType.DASHSCOPE, ModelServerType.ONLINE]
    if value == "image":
        return [ModelServerType.OPENAI, ModelServerType.DASHSCOPE]
    if value in ("vad", "denoise"):
        return []
    return [
        ModelServerType.OPENAI,
        ModelServerType.DASHSCOPE,
        ModelServerType.VLLM,
        ModelServerType.OLLAMA,
        ModelServerType.AWS,
    ]


# 角色
class RoleType(str, Enum):
    """
    消息角色枚举 system user assistant
    """

    SYSTEM = "system"
    USER = "user"  # "human"
    ASSISTANT = "assistant"  # 对应"ai"


# langchain消息类型
class LCRoleType(str, Enum):
    """
    langchain消息类型枚举 system human ai
    """

    SYSTEM = "system"
    USHUMAN = "human"
    AI = "ai"


class StreamStatus(str, Enum):
    """
    流式响应状态枚举 start stream end
    """

    START = "start"
    STREAM = "stream"
    END = "end"
    ERROR = "error"
