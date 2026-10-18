"""AI 模型接入模块 llm 表模型与请求/响应体定义"""

from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from module_ai.utils.llm.types import RoleType, LCRoleType, ModelType

class Message(BaseModel):
    """消息模型，与langchain_core.messages兼容"""

    role: RoleType = Field(
        RoleType.USER, description="消息角色：system、user、assistant"
    )
    content: str = Field(..., description="消息内容")
    additional_kwargs: dict = Field(default_factory=dict)

    @classmethod
    def from_langchain_message(cls, msg: BaseMessage) -> "Message":
        """从 LangChain 消息创建 Message 对象"""
        role_mapping = {
            LCRoleType.USHUMAN: RoleType.USER,
            LCRoleType.AI: RoleType.ASSISTANT,
            LCRoleType.SYSTEM: RoleType.SYSTEM,
        }

        role = role_mapping.get(msg.type, msg.type)
        return cls(
            role=role,
            content=str(msg.content),
            additional_kwargs=getattr(msg, "additional_kwargs", {}),
        )

    def to_langchain_message(self) -> BaseMessage:
        """转换为 LangChain 消息对象"""
        role_mapping = {
            RoleType.USER: HumanMessage,
            RoleType.ASSISTANT: AIMessage,
            RoleType.SYSTEM: SystemMessage,
        }

        msg_class = role_mapping.get(self.role, HumanMessage)
        return msg_class(content=self.content, additional_kwargs=self.additional_kwargs)


class ChatRequest(BaseModel):
    """聊天请求模型"""

    model_id: str = Field(..., description="模型配置ID或模型标识名称")
    messages: str | list[BaseMessage] = Field(
        ..., description="消息内容(字符串或消息列表, 列表项可为 dict/Message/LangChain 消息)"
    )
    streaming: bool = Field(False, description="是否启用流式响应")
    # 流式事件协议: legacy(旧 StreamChunkResponse) | agui(AG-UI 标准事件)
    event_protocol: str = Field("legacy", description="流式事件协议(legacy/agui)")

    @field_validator("messages", mode="before")
    @classmethod
    def validate_messages(cls, v):
        """
        验证并标准化messages字段(统一转为 LangChain 消息, 供模型直接调用)
        - 字符串 → 单条用户消息列表
        - 列表项为 dict/pydantic Message → 转 LangChain 消息
        - 空列表/其他形态保持原样(交由后续校验报错, 避免下标越界)
        """
        if isinstance(v, str):
            return [HumanMessage(content=v)]
        if isinstance(v, list):
            converted: list = []
            for item in v:
                if isinstance(item, BaseMessage):
                    converted.append(item)
                elif isinstance(item, Message):
                    converted.append(item.to_langchain_message())
                elif isinstance(item, dict):
                    converted.append(Message(**item).to_langchain_message())
                else:
                    converted.append(item)
            return converted
        return v


class EmbeddingRequest(BaseModel):
    """嵌入请求模型"""

    model_id: str = Field(..., description="模型配置ID或模型标识名称")
    texts: list[str] = Field(..., description="待嵌入的文本列表")


class CacheClearRequest(BaseModel):
    """缓存清除请求模型"""

    model_id: str | None = Field(
        None, description="模型配置ID或模型标识名称，为空则清除所有缓存"
    )


class TokenCountRequest(BaseModel):
    """token 计数请求模型"""

    texts: list[str] = Field(..., description="待计数的文本列表(批量)")

    @model_validator(mode="after")
    def check_size(self) -> "TokenCountRequest":
        """基础防护: 限制批量数量与单文本长度(前端聊天统计场景远小于此上限)"""
        if len(self.texts) > 200:
            raise ValueError("texts 数量不能超过 200")
        if any(len(t) > 100_000 for t in self.texts):
            raise ValueError("单条文本长度不能超过 100000 字符")
        return self


class TokenCountResponse(BaseModel):
    """token 计数响应模型"""

    counts: list[int] = Field(..., description="与请求 texts 顺序对应的 token 数列表")
    total: int = Field(0, description="全部文本 token 数合计")


class ModelChatCheckFormat(BaseModel):
    """
    校验模型格式化能力的模型
    """

    name: str = Field(..., description="名字")
    age: int = Field(..., description="年龄")


class ModelConfigCheckResponse(BaseModel):
    """
    校验模型配置的响应模型
    """

    is_valid: bool = Field(False, description="模型配置是否有效")
    is_format: bool = Field(False, description="模型支持格式化")


# 各模型类型支持的能力测试项: capability -> 中文名(与前端 capabilityOptionsFor 对齐)
# (vad/denoise 本地推理已下线, 不再提供能力测试)
MODEL_CAPABILITIES: dict[str, list[tuple[str, str]]] = {
    ModelType.CHAT.value: [("chat", "问答"), ("structured", "结构化"), ("vision", "多模态")],
    ModelType.EMBEDDINGS.value: [("embedding", "向量化")],
    ModelType.RERANK.value: [("rerank", "重排")],
    # 语音类: 用模拟音频对在线引擎做冒烟验证(通过=引擎可用不抛异常)
    ModelType.ASR.value: [("asr", "识别")],
    ModelType.TTS.value: [("tts", "合成")],
}


class ModelCapabilityTestItem(BaseModel):
    """单项能力测试结果"""

    capability: str = Field(..., description="能力标识(chat/structured/vision/embedding/rerank)")
    label: str = Field("", description="能力中文名")
    ok: bool = Field(False, description="是否通过")
    detail: str = Field("", description="结果摘要(通过时展示)")
    error: str = Field("", description="失败原因")
    elapsed: float = Field(0.0, description="耗时(秒)")
    suggest: dict | None = Field(
        None, description="附加建议(rerank: 检测到的分数范围与建议配置 score_min/score_max)"
    )


class ModelTestRequest(BaseModel):
    """模型能力测试请求"""

    model_id: str = Field(..., description="模型配置ID")
    capability: str | None = Field(None, description="仅测试指定能力(缺省测试该类型全部能力)")


class ModelCustomTestRequest(BaseModel):
    """模型自定义参数单独测试请求(chat/embeddings/rerank)"""

    model_id: str = Field(..., description="模型配置ID")
    question: str | None = Field(None, description="chat: 自定义提问内容")
    text: str | None = Field(None, description="embeddings: 待向量化的文本")
    query: str | None = Field(None, description="rerank: 检索 query")
    documents: list[str] | None = Field(None, description="rerank: 候选文档列表(逐条打分排序)")


class ModelCustomTestResponse(BaseModel):
    """模型自定义参数单独测试响应(单次真实调用结果)"""

    model_id: str = Field(..., description="模型配置ID")
    model_type: str = Field(..., description="模型类型(chat/embeddings/rerank)")
    capability: str = Field(..., description="测试能力标识")
    ok: bool = Field(False, description="是否成功")
    detail: str = Field("", description="结果摘要(向量维度/排序结论等)")
    answer: str = Field("", description="完整回答(chat)/识别文本等主体结果")
    results: list[dict] = Field(default_factory=list, description="明细列表(rerank 打分排序/ocr 行文本)")
    elapsed: float = Field(0.0, description="耗时(秒)")
    error: str = Field("", description="失败原因")


class TtsTestRequest(BaseModel):
    """TTS 单独测试请求(自定义文本合成语音)"""

    model_id: str = Field(..., description="模型配置ID")
    text: str = Field(..., description="待合成文本")
    speed: float = Field(1.0, description="语速(0.5~2.0)")


class ModelTestResponse(BaseModel):
    """模型能力测试响应(结果已持久化到 model_config.check_result)"""

    model_id: str = Field(..., description="模型配置ID")
    model_type: str = Field(..., description="模型类型")
    capabilities: list[ModelCapabilityTestItem] = Field(default_factory=list, description="各项能力测试结果")
    checked_at: datetime | None = Field(None, description="测试时间")
