"""知识库模块 conversation 表模型与请求/响应体定义"""

from sqlmodel import Column, DateTime, Field, SQLModel, JSON
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel

class ConversationBase(SQLModel):
    """对话基础模型"""

    title: str = Field(..., max_length=200, description="对话标题")
    agent_id: str | None = Field(default=None, max_length=50, description="智能体ID(当前为空)")


class Conversation(ConversationBase, table=True):
    """对话数据库模型"""

    __tablename__ = "conversation"

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        primary_key=True,
        index=True,
        description="唯一标识符",
    )
    user_id: str = Field(..., max_length=50, index=True, description="用户ID")
    project_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="关联知识库(项目)ID列表",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="创建时间",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        ),
        description="最后更新时间",
    )


class ConversationCreate(SQLModel):
    """创建对话的请求模型"""

    title: str = Field(..., max_length=200, description="对话标题")
    agent_id: str | None = Field(default=None, max_length=50, description="智能体ID")
    project_ids: list[str] = Field(default_factory=list, description="关联知识库ID列表")


class ConversationUpdate(SQLModel):
    """更新对话的请求模型"""

    title: str | None = Field(None, max_length=200, description="对话标题")
    agent_id: str | None = Field(None, max_length=50, description="智能体ID")
    project_ids: list[str] | None = Field(None, description="关联知识库ID列表")


class ConversationResponse(SQLModel):
    """对话响应模型"""

    id: str = Field(..., description="唯一标识符")
    user_id: str = Field(..., description="用户ID")
    title: str = Field(..., description="对话标题")
    agent_id: str | None = Field(default=None, description="智能体ID")
    project_ids: list[str] = Field(default_factory=list, description="关联知识库ID列表")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class TempFilePayload(BaseModel):
    """会话临时文件(前端经 parse-temp-file 解析后随消息回传, 不入知识库不入向量)"""

    name: str = Field(..., max_length=255, description="文件名(展示与溯源用)")
    content: str = Field(..., description="解析后的文本内容")


class ChatRequest(BaseModel):
    """聊天请求"""

    # 交互卡片响应时可为空(纯点击提交), 由 service 生成可读兜底文案
    message: str = ""
    project_ids: list[str] = []
    deep_thinking: bool = False
    rerank_limit: int = Field(default=20, description="Rerank精排返回的最大结果数") # 新增
    # 联网搜索开关: None=跟随通用配置"网页搜索"组的 rag_enable 全局默认; true/false 请求级覆盖
    enable_websearch: bool | None = Field(
        default=None, description="是否启用网络搜索(None=跟随通用配置全局开关)"
    )
    # 临时文件: 本次问答上下文(以 SystemMessage 注入本 run, 经 checkpointer 持久可多轮追问)
    temp_files: list[TempFilePayload] = Field(
        default_factory=list, description="临时文件列表(不入知识库, 与知识库/联网开关可组合)"
    )
    # 交互响应: {interaction_id, action, value}, 需与 checkpointer 中待响应请求匹配才生效
    interaction_response: dict | None = Field(
        default=None, description="交互卡片响应(澄清/知识缺口补充)"
    )
    # 注: 本接口已统一输出 AG-UI 协议事件流(官方 SDK ag-ui-protocol), 不再有旧协议分支

class ConversationSummary(BaseModel):
    """对话摘要结构化模型"""
    title: str = Field(default="新对话", description="不超过20字的对话标题")
    summary: str = Field(default="", description="不超过100字的对话总结")

class SummaryState(dict):
    """总结节点的状态"""
    history_text: str
    summary: ConversationSummary | None = None