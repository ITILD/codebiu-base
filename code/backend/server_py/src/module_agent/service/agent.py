"""智能体业务服务(REQ-013): CRUD + 可见性控制 + 内置种子

可见性规则:
- 普通用户: 公开(is_public)或自己创建的 Agent 可见可用; 仅能编辑/删除自己的
- 管理员(agent:manage): 全部可见可改, 内置 Agent 可编辑但不可删除
"""

import logging

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_agent.dao.agent import AgentDao
from module_agent.do.agent import Agent, AgentCreate, AgentResponse, AgentUpdate
from module_agent.skills import builtin as builtin_skills  # noqa: F401 (导入即注册)
from module_agent.skills.registry import SKILLS, list_skill_infos

logger = logging.getLogger(__name__)

# 内置智能体固定ID(幂等种子按此 upsert)
BUILTIN_CHAT_ID = "builtin_chat"
BUILTIN_AGENT_ID = "builtin_agent"

# 内置默认提示词(自建 Agent 的 default_prompt 为空时回退)
DEFAULT_CHAT_PROMPT = "你是一个乐于助人的 AI 助手, 请准确、简洁地回答用户问题。"
DEFAULT_AGENT_PROMPT = (
    "你是一个能干的智能体, 可以调用工具获取外部信息后再回答。"
    "当用户问题需要联网信息、图片文字、文件位置或知识库内容时, 请主动调用对应工具; "
    "工具结果不足以回答时如实说明。回答请准确、简洁。"
)


class AgentService:
    def __init__(self, agent_dao: AgentDao | None = None):
        """依赖注入构造器"""
        self.agent_dao = agent_dao or AgentDao()

    # ── 校验 ──

    @staticmethod
    def _validate_skills(skills: list[str]) -> None:
        """技能名单必须全部在注册表中"""
        unknown = [s for s in skills if s not in SKILLS]
        if unknown:
            raise BusinessError(f"未知技能: {', '.join(unknown)}(可选: {', '.join(SKILLS)})")

    # ── 查询 ──

    @staticmethod
    def list_skills() -> list[dict]:
        """技能注册表清单"""
        return list_skill_infos()

    async def list_for_user(self, user_id: str) -> list[AgentResponse]:
        """用户可见的智能体列表"""
        agents = await self.agent_dao.list_visible(user_id=user_id)
        return [AgentResponse.model_validate(a, from_attributes=True) for a in agents]

    async def list_all(self) -> list[AgentResponse]:
        """全部智能体(管理 scope)"""
        agents = await self.agent_dao.list_all()
        return [AgentResponse.model_validate(a, from_attributes=True) for a in agents]

    async def get_for_user(
        self, agent_id: str, user_id: str, is_admin: bool = False
    ) -> AgentResponse:
        """查询单个智能体(可见性校验)"""
        agent = await self._get_visible(agent_id, user_id, is_admin)
        return AgentResponse.model_validate(agent, from_attributes=True)

    async def _get_visible(
        self, agent_id: str, user_id: str, is_admin: bool = False
    ) -> Agent:
        """取可见的 Agent 行(不可见/不存在统一 404, 不泄漏存在性)"""
        agent = await self.agent_dao.get(agent_id)
        if agent is None or not (
            is_admin or agent.is_public or agent.owner_user_id == user_id
        ):
            raise NotFoundError(f"未找到ID为 {agent_id} 的智能体")
        return agent

    # ── 写操作 ──

    async def create(self, user_id: str, req: AgentCreate) -> AgentResponse:
        """创建智能体(登录即可, 自建 Agent 归属本人)"""
        self._validate_skills(req.skills)
        agent = Agent(
            name=req.name,
            description=req.description,
            default_prompt=req.default_prompt,
            default_project_ids=req.default_project_ids,
            skills=req.skills,
            owner_user_id=user_id,
            is_public=req.is_public,
            is_builtin=False,
        )
        agent = await self.agent_dao.add(agent)
        return AgentResponse.model_validate(agent, from_attributes=True)

    async def update(
        self, agent_id: str, user_id: str, req: AgentUpdate, is_admin: bool = False
    ) -> AgentResponse:
        """更新智能体(仅创建者; 内置 Agent 仅管理员可改)"""
        agent = await self._get_visible(agent_id, user_id, is_admin)
        if agent.owner_user_id != user_id and not is_admin:
            raise BusinessError("仅创建者或管理员可修改该智能体")
        if req.skills is not None:
            self._validate_skills(req.skills)
            agent.skills = req.skills
        if req.name is not None:
            agent.name = req.name
        if req.description is not None:
            agent.description = req.description
        if req.default_prompt is not None:
            agent.default_prompt = req.default_prompt
        if req.default_project_ids is not None:
            agent.default_project_ids = req.default_project_ids
        if req.is_public is not None:
            agent.is_public = req.is_public
        agent = await self.agent_dao.update(agent)
        return AgentResponse.model_validate(agent, from_attributes=True)

    async def delete(
        self, agent_id: str, user_id: str, is_admin: bool = False
    ) -> None:
        """删除智能体(仅创建者; 内置不可删)"""
        agent = await self._get_visible(agent_id, user_id, is_admin)
        if agent.is_builtin:
            raise BusinessError("内置智能体不可删除")
        if agent.owner_user_id != user_id and not is_admin:
            raise BusinessError("仅创建者或管理员可删除该智能体")
        await self.agent_dao.delete(agent)

    # ── 内置种子 ──

    async def seed_builtin_agents(self) -> None:
        """幂等播种内置双 Agent(存在则跳过, 不覆盖管理员的后续修改)"""
        for agent_id, name, description, prompt, skills in (
            (
                BUILTIN_CHAT_ID,
                "通用助手",
                "纯对话助手, 不挂载技能, 直接回答问题",
                DEFAULT_CHAT_PROMPT,
                [],
            ),
            (
                BUILTIN_AGENT_ID,
                "全能智能体",
                "挂载全部只读技能(联网搜索/图片OCR/文件检索/知识库问答)",
                DEFAULT_AGENT_PROMPT,
                list(SKILLS.keys()),
            ),
        ):
            if await self.agent_dao.get(agent_id) is not None:
                continue
            await self.agent_dao.add(
                Agent(
                    id=agent_id,
                    name=name,
                    description=description,
                    default_prompt=prompt,
                    default_project_ids=[],
                    skills=skills,
                    owner_user_id="system",
                    is_public=True,
                    is_builtin=True,
                )
            )
            logger.info(f"内置智能体已播种: {name}({agent_id})")
