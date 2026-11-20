"""知识库模块 rag_chat 表模型与请求/响应体定义"""

import logging
from typing import TypedDict
from enum import StrEnum
from uuid import uuid4
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from module_rag.do.project_document_chunk import ProjectDocumentChunkSearchResponse
logger = logging.getLogger(__name__)


class StreamEventType(StrEnum):
    """流式输出事件分类"""

    LLM_THINKING = "llm_thinking"  # LLM 推理/思考过程 (reasoning tokens)
    AGENT_THINKING = "agent_thinking"  # 策略思考过程 意图识别等
    # 思考结论的结论（人工或工具参与整理的信息）
    AGENT_THINKING_CONCLUSION = "agent_thinking_conclusion"
    TOOL_CALL = "tool_call"  # 工具调用（知识库检索等）
    FILE_GEN = "file_gen"  # 文件生成
    ANSWER = "answer"  # 正式回答
    STATUS = "status"  # 状态更新（进度提示）
    ERROR = "error"  # 错误信息
    TEMP_FILE = "temp_file"  # 用户上传的临时文件附件标记(仅用户消息 blocks, 前端渲染附件芯片)
    INTERACTION = "interaction"  # 用户交互请求(信息澄清/知识缺口补充等, AG-UI 模式经 CUSTOM rag.interaction 下发)
    MODE_DECISION = "mode_decision"  # 执行模式决策结论(模式即 Agent, AG-UI 模式经 CUSTOM rag.mode_decision 下发)


class ConversationSummary(BaseModel):
    """对话总结结构化输出模型(用于 LLM 结构化输出, 生成对话标题和摘要)"""

    title: str = Field(
        default="",
        description="简短的对话标题(不超过20字，概括对话主题)",
    )
    summary: str = Field(
        default="",
        description="对话总结(不超过100字，概括对话关键信息)",
    )


class SummaryState(MessagesState):
    """对话总结 graph 状态"""

    user_id: str
    summary: ConversationSummary | None


class RagHelpInfo(BaseModel):
    """RAG 帮助信息模型"""

    intent: str = Field(default="", description="用户意图")
    vector_search: str = Field(default="", description="对向量搜索有帮助的语句")
    full_text_search: str = Field(default="", description="用于全文检索语句")
    web_search: str = Field(
        default="",
        description="用于联网搜索引擎的检索语句(面向搜索引擎的关键词组合, 简洁精准)",
    )
    is_need_external_info: bool = Field(
        default=True, description="是否需要外部信息回答最新问题"
    )
    needs_clarification: bool = Field(
        default=False,
        description="最新问题信息不足(指代不明/缺少关键实体), 需要用户澄清后才能有效检索",
    )
    clarify_question: str = Field(
        default="",
        description="向用户提出的澄清问题(needs_clarification 时使用, 需具体明确)",
    )
    complexity: str = Field(
        default="simple",
        description=(
            "问题复杂度信号(模式即 Agent 的意图信号, REQ-019 §2.2): "
            "simple=简单单问 / complex=复合问题(需多步或多方面取证) / "
            "cross_source=需跨源交叉验证(知识库+网络或多库对比)"
        ),
    )


# ──────────────────────────────────────────────
# 联网检索引用
# ──────────────────────────────────────────────


class WebCitation(BaseModel):
    """RAG 联网检索引用(网络搜索结果, 可与知识库片段合并精排)

    content 为派生文本(标题+摘要), 供 Rerank 候选统一取文本用
    """

    title: str = Field(default="", description="结果标题")
    url: str = Field(default="", description="结果链接")
    source: str = Field(default="", description="来源站点域名")
    description: str = Field(default="", description="摘要描述")
    score: float | None = Field(default=None, description="Rerank 相关度得分(未精排时为空)")

    @property
    def content(self) -> str:
        """派生文本: 标题+摘要(与知识片段同构, 供 rerank_candidates 统一提取)"""
        return f"{self.title}\n{self.description}".strip()


class InteractionKind(StrEnum):
    """交互请求类型(缺失内容补充/信息澄清)"""

    CLARIFY = "clarify"  # 问题信息不足, 请用户澄清
    KNOWLEDGE_GAP = "knowledge_gap"  # 知识库未检索到相关内容, 请用户补充/选择继续方式


class InteractionOption(BaseModel):
    """交互请求候选项"""

    label: str = Field(..., description="选项展示文案")
    value: str = Field(..., description="选项值(提交时作为 action/value 回传)")
    description: str = Field("", description="选项说明")


class InteractionSpec(BaseModel):
    """用户交互请求规格(AG-UI 模式经 CUSTOM rag.interaction 下发, 前端渲染交互卡片)"""

    interaction_id: str = Field(
        default_factory=lambda: uuid4().hex, description="交互请求唯一ID(响应时校验)"
    )
    kind: InteractionKind = Field(..., description="交互类型(clarify/knowledge_gap)")
    title: str = Field(..., description="卡片标题")
    question: str = Field(..., description="向用户提出的问题")
    options: list[InteractionOption] = Field(
        default_factory=list, description="候选项(空则纯文本输入)"
    )
    allow_text: bool = Field(True, description="是否允许自由文本输入")
    text_placeholder: str = Field("", description="文本输入占位提示")
    context: dict = Field(default_factory=dict, description="附加上下文(检索语句/结果数等)")


class RagChatState(MessagesState):
    """RAG 聊天状态(扩展 MessagesState)"""

    project_ids: list[str]
    # 仅临时知识库自动并入检索范围(用户未显式选择知识库): 检索零命中降级直接回答
    kb_auto_only: bool
    # 用户问答知识库(temp 分类, 会话附件入库)ID; 空串=用户尚未建库/本轮禁用知识库
    temp_kb_id: str
    # 本轮消息附件文件名: 非空时优先定向检索问答知识库, 保证上传文件必被召回
    attachment_names: list[str]
    user_id: str
    rag_help_info: RagHelpInfo | None
    knowledge_context_list: list[ProjectDocumentChunkSearchResponse] | None
    rerank_limit: int  # Rerank 精排返回的最大结果数
    enable_websearch: bool  # 本轮是否启用网络搜索(请求级覆盖 → 全局 websearch.rag_enable)
    web_results: list[WebCitation] | None  # 网络搜索结果(与知识片段合并精排后, 按相关度序)
    web_search_error: str | None  # 网络搜索失败原因(失败静默降级仅用知识库, 过程区块提示)
    search_error: str | None  # 知识库检索失败原因(None=检索正常), 供过程区块区分"失败"与"无结果"
    # ── REQ-019 模式即 Agent(§2.2) ──
    agent_key: str  # 本轮执行智能体(内置: builtin_fast / builtin_thinking)
    agent_chat_modes: dict  # 智能体库中 chat_modes(运行参数, 管理员可调)
    requested_mode: str  # 用户请求模式: auto / fast / thinking
    exec_mode: str  # 实际执行模式: fast / thinking / deep
    mode_reason: str  # 模式决策依据(可观测, 前端展示"为什么是这个模式")
    explicit_deep: bool  # 显式深度信号(意图强信号, 供模式解析升级到 deep)
    conversation_id: str  # 会话ID(技能上下文注入)
    mode_config: dict | None  # 解析出的执行模式参数(内置 Agent chat_modes 快照, §2.1)
    deep_evidence: list[dict] | None  # 深度取证证据池(工具结果 → 证据)
    deep_events: list[dict] | None  # 深度执行过程事件(工具调用/熔断等)
    deep_stop_reason: str | None  # 深度执行收尾原因
    skill_context: str | None  # 技能产出上下文(与检索证据区分, §3.3)
    # ── 用户交互(跨 run 持久于 checkpointer) ──
    pending_interaction: dict | None  # 待响应的交互请求(InteractionSpec 序列化)
    interaction_response: dict | None  # 本次请求携带的交互响应 {interaction_id, kind, action, value}
    supplement_content: str | None  # 用户补充的知识内容(knowledge_gap 响应), 注入 chat 上下文
    # 用量元数据(chat 节点写入): {model_name, prompt_tokens}, 供回答完成后旁路记账
    usage_meta: dict | None


class StreamOne(BaseModel):
    content: str = Field(..., description="模型返回的内容")
    # 默认空串: chat_stream 的回退提示/错误事件不携带节点名, 必填会抛 ValidationError 中断流
    node_name: str = Field("", description="节点名称")
    stream_event_type: StreamEventType = Field(
        StreamEventType.ANSWER, description="流式输出事件分类"
    )
    # 结构化载荷(检索结果/意图结论/交互请求), AG-UI 协议层消费, 旧协议前端忽略
    data: dict | None = Field(None, description="结构化事件载荷")

# 业务
class GraphEvent(StrEnum):
    """LangGraph 原始事件名"""

    MODEL_STREAM = "on_chat_model_stream"
    NODE_START = "on_chain_start"
    NODE_END = "on_chain_end"


class GraphNode(StrEnum):
    """RAG 图节点名"""

    INTENT = "intent_analysis"
    SEARCH = "knowledge_search"
    CHAT = "chat"
    SUMMARY = "summarize"
    CLARIFY = "clarify_interaction"  # 意图澄清交互(等待用户补充信息)
    GAP = "knowledge_gap"  # 知识缺口交互(检索无结果, 等待用户补充内容/选择继续方式)
    RESOLVE_MODE = "resolve_mode"  # 模式解析(REQ-019 §2.2: requested → exec)
    DEEP = "deep_agent"  # 深度执行节点(有界 ReAct 取证, §3.3)


# 节点名 → 业务流事件类型
NODE_EVENT_MAP: dict[GraphNode, StreamEventType] = {
    GraphNode.INTENT: StreamEventType.AGENT_THINKING,
    GraphNode.SEARCH: StreamEventType.TOOL_CALL,
    GraphNode.CHAT: StreamEventType.ANSWER,
    GraphNode.RESOLVE_MODE: StreamEventType.AGENT_THINKING,
    GraphNode.DEEP: StreamEventType.TOOL_CALL,
}

# 节点名 → 前端状态提示
NODE_STATUS_MAP: dict[GraphNode, str] = {
    GraphNode.INTENT: "正在分析意图…",
    GraphNode.SEARCH: "正在检索知识库…",
    GraphNode.CHAT: "正在生成回答…",
    GraphNode.CLARIFY: "正在确认补充信息…",
    GraphNode.GAP: "正在评估知识覆盖…",
    GraphNode.RESOLVE_MODE: "正在决策执行模式…",
    GraphNode.DEEP: "正在多轮取证…",
}

# 知识库检索数量上限
SEARCH_LIMIT = 20