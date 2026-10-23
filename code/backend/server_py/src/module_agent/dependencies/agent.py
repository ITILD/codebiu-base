"""智能体模块 FastAPI 依赖注入(REQ-013)"""

from module_agent.dao.agent import AgentDao
from module_agent.service.agent import AgentService
from module_agent.service.runner import AgentRunnerService
from module_rag.service.chat_message import ChatMessageService
from module_rag.service.conversation import ConversationService
from module_rag.service.user_model import UserModelService


def get_agent_service() -> AgentService:
    """智能体 CRUD 服务"""
    return AgentService()


def get_agent_runner_service() -> AgentRunnerService:
    """智能体执行循环服务"""
    return AgentRunnerService(
        agent_dao=AgentDao(),
        chat_message_service=ChatMessageService(),
        conversation_service=ConversationService(),
        user_model_service=UserModelService(),
    )
