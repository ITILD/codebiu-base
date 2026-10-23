"""智能体控制器(REQ-013): 助手 CRUD / 技能清单 / 智能体对话(SSE)

- 助手管理: 自建 Agent 登录即可(个人数据隔离); 管理端点走 agent:manage
- 对话: 复用 rag 会话(conversation.agent_id 标记)与 rag:chat:write 权限,
  SSE 走 agui_event_generator(与 rag 聊天同一 AG-UI 协议链路)
"""

import logging

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from module_agent.config.server import module_app
from module_agent.dependencies.agent import get_agent_runner_service, get_agent_service
from module_agent.do.agent import AgentCreate, AgentResponse, AgentUpdate
from module_agent.service.runner import AgentChatRequest, AgentRunnerService
from module_agent.service.agent import AgentService
from module_ai.utils.llm.stream.sse import agui_event_generator
from module_authorization.dependencies.auth import get_current_user_id
from module_authorization.dependencies.permission import check_permission, require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/skills", summary="技能注册表清单", response_model=list[dict])
async def list_skills(
    current_user_id: str = Depends(get_current_user_id),
    agent_service: AgentService = Depends(get_agent_service),
) -> list[dict]:
    """内置技能清单(名称/描述/能力分级, 供助手编辑器勾选)"""
    return agent_service.list_skills()


@router.get("/agents", summary="我可见的智能体列表", response_model=list[AgentResponse])
async def list_agents(
    current_user_id: str = Depends(get_current_user_id),
    agent_service: AgentService = Depends(get_agent_service),
) -> list[AgentResponse]:
    """公开 + 本人创建的智能体(对话侧选择器用)"""
    return await agent_service.list_for_user(current_user_id)


@router.get("/agents/all", summary="全部智能体(管理)", response_model=list[AgentResponse])
async def list_all_agents(
    current_user_id: str = Depends(require_permission("agent", "manage", "read")),
    agent_service: AgentService = Depends(get_agent_service),
) -> list[AgentResponse]:
    """全部智能体(含他人私有, 助手管理页用)"""
    return await agent_service.list_all()


@router.get("/agents/{agent_id}", summary="智能体详情", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user_id: str = Depends(get_current_user_id),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    """单个智能体(公开或本人创建)"""
    is_admin = await check_permission(current_user_id, "agent", "manage", "read")
    return await agent_service.get_for_user(agent_id, current_user_id, is_admin)


@router.post("/agents", summary="创建智能体", response_model=AgentResponse)
async def create_agent(
    req: AgentCreate,
    current_user_id: str = Depends(get_current_user_id),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    """创建智能体(登录即可, 技能名单须全部在注册表内)"""
    return await agent_service.create(current_user_id, req)


@router.put("/agents/{agent_id}", summary="更新智能体", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    req: AgentUpdate,
    current_user_id: str = Depends(get_current_user_id),
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    """更新智能体(创建者或管理员; 内置智能体仅管理员可改)"""
    is_admin = await check_permission(current_user_id, "agent", "manage", "update")
    return await agent_service.update(agent_id, current_user_id, req, is_admin)


@router.delete("/agents/{agent_id}", summary="删除智能体")
async def delete_agent(
    agent_id: str,
    current_user_id: str = Depends(get_current_user_id),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict:
    """删除智能体(创建者或管理员; 内置不可删)"""
    is_admin = await check_permission(current_user_id, "agent", "manage", "delete")
    await agent_service.delete(agent_id, current_user_id, is_admin)
    return {"detail": "已删除"}


@router.post("/chat/{conversation_id}/chat", summary="智能体流式对话(SSE, AG-UI 协议)")
async def agent_chat_stream(
    conversation_id: str,
    chat_request: AgentChatRequest,
    request_obj: Request,
    current_user_id: str = Depends(require_permission("rag", "chat", "write")),
    runner_service: AgentRunnerService = Depends(get_agent_runner_service),
) -> EventSourceResponse:
    """智能体流式对话(tool-calling 循环, 事件流与 rag 聊天同一 AG-UI 协议)

    - 会话复用 rag conversation 表(agent_id 标记), 归属校验在执行循环内
    - 工具调用轮的过程区块(TOOL_CALL)与推理流(LLM_THINKING)随流下发
    """
    responses = runner_service.chat_stream(
        conversation_id=conversation_id,
        user_id=current_user_id,
        agent_id=chat_request.agent_id,
        request=chat_request,
    )
    return EventSourceResponse(
        agui_event_generator(
            responses,
            request_obj,
            thread_id=conversation_id,
            initial_state={
                "conversationId": conversation_id,
                "agentId": chat_request.agent_id,
            },
        ),
        media_type="text/event-stream",
    )


# 注册路由(挂在 /agent 前缀下)
module_app.include_router(router, tags=["智能体"])
