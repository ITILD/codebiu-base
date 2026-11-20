"""
RAG 聊天控制器
- 流式聊天(SSE)：从 conversation.py 迁移过来
- 问答附件上传：入库用户默认临时知识库并派发解析任务
- 对话总结：压缩历史消息并生成标题
"""

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sse_starlette import EventSourceResponse
from common.utils.fastapi_ex.exceptions import BusinessError
from module_file.do.filesystem import (
    EntryCreateRequest,
    MultipartCompleteRequest,
    MultipartInitRequest,
    MultipartInitResponse,
    MultipartPartInfo,
    UploadModeResponse,
)
from module_file.dependencies.filesystem import get_file_service
from module_file.service.filesystem import FileService
from module_rag.do.rag_chat import ConversationSummary
from module_rag.do.conversation import ChatRequest
from module_rag.do.project_document import ProjectDocumentResponse
from module_rag.controller.project_document import _dispatch_parse_task
from module_rag.dependencies.project import get_project_service
from module_rag.dependencies.project_document import get_project_document_service
from module_rag.service.project import ProjectService
from module_rag.service.project_document import ProjectDocumentService
from module_rag.service.rag_chat import RagChatService
from module_rag.service.chat_attachment import ChatAttachmentService
from module_rag.dependencies.rag_chat import get_rag_chat_service_single
from module_task.dependencies.task import get_task_queue_service
from module_task.service.task import TaskQueueService
from module_authorization.dependencies.auth import get_current_user_id
from module_authorization.dependencies.permission import require_permission
from module_rag.config.server import module_app
from module_ai.utils.llm.stream.sse import agui_event_generator
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/attachments",
    summary="上传问答附件(存入个人默认临时知识库并解析入库)",
    response_model=ProjectDocumentResponse,
)
async def upload_chat_attachment(
    file: UploadFile = File(..., description="附件文件(与知识库白名单一致: 版式文档/图片/纯文本)"),
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    task_service: TaskQueueService = Depends(get_task_queue_service),
    project_service: ProjectService = Depends(get_project_service),
    document_service: ProjectDocumentService = Depends(get_project_document_service),
) -> ProjectDocumentResponse:
    """
    上传问答附件: 自动获取/创建用户 temp 分类临时知识库, 经统一存储登记为
    project_document 并派发异步解析任务(解析→分块→向量化, 与知识库文档同链路);
    入库进度经 GET /rag/project-documents/{document_id}/progress 轮询,
    完成后问答检索范围自动并入该库
    :param file: 上传的附件文件
    :return: 文档元数据(parse_task_warning 携带解析任务派发警告)
    """
    service = ChatAttachmentService(project_service, document_service)
    document = await service.upload(file, current_user_id)
    response = ProjectDocumentResponse.model_validate(document.model_dump())
    response.parse_task_warning = await _dispatch_parse_task(
        service.document_service, task_service, document, current_user_id
    )
    return response


@router.get(
    "/attachments/upload-mode",
    summary="查询问答附件上传模式(direct预签名直传/proxy服务端中转)",
    response_model=UploadModeResponse,
)
async def get_attachment_upload_mode(
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    project_service: ProjectService = Depends(get_project_service),
    document_service: ProjectDocumentService = Depends(get_project_document_service),
) -> UploadModeResponse:
    """查询问答附件上传模式(前端上传前获取并缓存)"""
    service = ChatAttachmentService(project_service, document_service)
    return service.get_upload_mode()


@router.post(
    "/attachments/multipart/init",
    summary="初始化问答附件预签名上传(同名自动加序号/内容已存在时秒传)",
    response_model=MultipartInitResponse,
)
async def init_attachment_multipart(
    req: MultipartInitRequest,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    project_service: ProjectService = Depends(get_project_service),
    document_service: ProjectDocumentService = Depends(get_project_document_service),
) -> MultipartInitResponse:
    """
    初始化问答附件上传: 登记到用户临时知识库, 返回直传预签名URL或中转凭证
    :param req: 初始化请求(文件名/大小/SHA-256)
    :return: 会话凭证(含服务端确认的落库文件名)
    """
    service = ChatAttachmentService(project_service, document_service)
    return await service.init_multipart(req, current_user_id)


@router.put(
    "/attachments/multipart/{upload_id}/parts/{part_number}",
    summary="上传问答附件分片(proxy中转模式)",
    response_model=MultipartPartInfo,
)
async def upload_attachment_part(
    upload_id: str,
    part_number: int,
    request: Request,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    file_service: FileService = Depends(get_file_service),
) -> MultipartPartInfo:
    """中转上传单个分片(direct 模式前端直传对象存储,不经服务端)"""
    content: bytes = await request.body()
    if not content:
        raise BusinessError("分片内容不能为空")
    return await file_service.upload_multipart_part(upload_id, part_number, content)


@router.post(
    "/attachments/multipart/{upload_id}/complete",
    summary="完成问答附件上传(对账合并并登记文档)",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectDocumentResponse,
)
async def complete_attachment_multipart(
    upload_id: str,
    req: MultipartCompleteRequest,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    project_service: ProjectService = Depends(get_project_service),
    document_service: ProjectDocumentService = Depends(get_project_document_service),
    task_service: TaskQueueService = Depends(get_task_queue_service),
) -> ProjectDocumentResponse:
    """
    合并分片并登记为问答附件文档, 成功后自动派发解析任务
    :param upload_id: 分片会话凭证
    :param req: 完成请求(文件名/分片清单)
    :return: 文档元数据(parse_task_warning 携带解析任务派发警告)
    """
    service = ChatAttachmentService(project_service, document_service)
    document = await service.complete_multipart(upload_id, req, current_user_id)
    response = ProjectDocumentResponse.model_validate(document.model_dump())
    response.parse_task_warning = await _dispatch_parse_task(
        document_service, task_service, document, current_user_id
    )
    return response


@router.post(
    "/attachments/upload-complete",
    summary="问答附件秒传登记(内容已存在时直接建文档)",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectDocumentResponse,
)
async def instant_attachment(
    req: EntryCreateRequest,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    project_service: ProjectService = Depends(get_project_service),
    document_service: ProjectDocumentService = Depends(get_project_document_service),
    task_service: TaskQueueService = Depends(get_task_queue_service),
) -> ProjectDocumentResponse:
    """
    基于已存在的内容记录创建问答附件文档(init 返回 is_existing=True 后调用)
    :param req: 登记请求(文件名/内容SHA-256/大小)
    :return: 文档元数据(parse_task_warning 携带解析任务派发警告)
    """
    service = ChatAttachmentService(project_service, document_service)
    document = await service.create_from_content(req, current_user_id)
    response = ProjectDocumentResponse.model_validate(document.model_dump())
    response.parse_task_warning = await _dispatch_parse_task(
        document_service, task_service, document, current_user_id
    )
    return response


@router.post("/{conversation_id}/chat", summary="流式聊天(SSE, AG-UI 协议)")
async def chat_stream(
    conversation_id: str,
    chat_request: ChatRequest,
    request_obj: Request,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    rag_chat_service: RagChatService = Depends(get_rag_chat_service_single),
) -> EventSourceResponse:
    """
    流式聊天接口(SSE, AG-UI 协议)

    AG-UI(Agent User Interaction Protocol)是事件驱动的开放交互协议,
    事件模型由官方 SDK `ag-ui-protocol` 提供, 本端点输出标准事件流:
    - 生命周期 RUN_STARTED/RUN_FINISHED/RUN_ERROR + STEP_*(步骤=图节点)
    - 正文 TEXT_MESSAGE_* 增量流; 推理 REASONING_* 流
    - 检索 TOOL_CALL_*(RESULT 携带结构化引用溯源)
    - CUSTOM 业务扩展(rag.status 进度 / rag.intent_result 意图结论 /
      rag.interaction 交互卡片)

    业务能力:
    - 根据对话ID获取上下文(langgraph postgres checkpointer)
    - 支持传入知识库列表，有内容时先做意图分析
    - 支持 interaction_response 响应交互卡片(澄清/知识缺口补充)续跑流程
    """
    # 不做 try/except 包装: 建流前的校验错误(BizError 等)由全局异常处理器映射状态码,
    # 流式体内的异常由 agui_event_generator 转为 RUN_ERROR 事件推送
    responses = rag_chat_service.chat_stream(
        conversation_id=conversation_id, user_id=current_user_id, chat_request=chat_request
    )
    return EventSourceResponse(
        agui_event_generator(
            responses,
            request_obj,
            # threadId 即会话ID: AG-UI 语义的会话线程标识
            thread_id=conversation_id,
            # 初始状态快照(STATE_SNAPSHOT): 前端可据此恢复会话上下文
            initial_state={
                "conversationId": conversation_id,
                "projectIds": chat_request.project_ids,
                "agentId": chat_request.agent_id,
            },
        ),
        media_type="text/event-stream",
    )


@router.post(
    "/{conversation_id}/summarize",
    summary="总结历史对话(压缩消息)并生成标题",
    response_model=ConversationSummary,
)
async def summarize_conversation(
    conversation_id: str,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    rag_chat_service: RagChatService = Depends(get_rag_chat_service_single),
):
    """
    对指定会话执行结构化总结并持久化: 生成的新标题写入对话记录,
    总结失败时降级返回默认空摘要
    - 从 checkpointer 拉取完整消息历史
    - 调用 LLM 生成对话摘要和简短标题
    - 持久化更新对话标题
    """
    return await rag_chat_service.summarize_conversation(conversation_id, current_user_id)


# 注册路由(挂在 /rag/rag-chat 前缀下)
module_app.include_router(router, prefix="/rag-chat", tags=["RAG聊天"])
