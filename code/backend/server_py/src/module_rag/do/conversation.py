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


class ChatRequest(BaseModel):
    """聊天请求"""

    # 交互卡片响应时可为空(纯点击提交), 由 service 生成可读兜底文案
    message: str = ""
    # 智能体ID: 问答页选择的智能体决定执行方式(快速=固定 RAG / 思考=ReAct),
    # 未传时回退会话绑定的 agent_id
    agent_id: str | None = Field(
        default=None, description="智能体ID(决定执行策略与运行参数)"
    )
    project_ids: list[str] = []
    mode: str | None = Field(
        default=None,
        description=(
            "兼容字段: 未选智能体时的对话模式; 选择内置智能体时由 agent_id 决定, 忽略此值"
        ),
    )
    # 知识库范围(前端三态): auto=自动匹配有权限的知识库(未勾选时后端自动解析) /
    # manual=仅用 project_ids(可为空=本轮不检索) / off=禁用知识库;
    # None=兼容旧客户端(空 project_ids 视为本轮不检索)
    kb_mode: str | None = Field(
        default=None, description="知识库范围模式(auto/manual/off)"
    )
    rerank_limit: int = Field(default=20, description="Rerank精排返回的最大结果数") # 新增
    # 联网搜索开关: None=跟随通用配置"网页搜索"组的 rag_enable 全局默认; true/false 请求级覆盖
    enable_websearch: bool | None = Field(
        default=None, description="是否启用网络搜索(None=跟随通用配置全局开关)"
    )
    # 本条消息附件文件名(附件已入库个人默认临时知识库, 此处仅作消息区块标记,
    # 检索范围由后端自动并入临时库, 与知识库/联网开关可组合)
    attachments: list[str] = Field(
        default_factory=list, description="附件文件名列表(已入库, 用于用户消息附件标记)"
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