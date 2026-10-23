"""智能体数据访问层(REQ-013)"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from module_agent.do.agent import Agent


class AgentDao:
    @DaoRel
    async def add(self, data: Agent, session: AsyncSession | None = None) -> Agent:
        """新增智能体"""
        session.add(data)
        await session.flush()
        return data

    @DaoRel
    async def get(self, agent_id: str, session: AsyncSession | None = None) -> Agent | None:
        """按ID查询"""
        statement = select(Agent).where(Agent.id == agent_id)
        return (await session.exec(statement)).first()

    @DaoRel
    async def list_visible(
        self, user_id: str, session: AsyncSession | None = None
    ) -> list[Agent]:
        """查询用户可见的智能体(公开 + 自己创建, 创建时间正序内置优先)"""
        statement = (
            select(Agent)
            .where((Agent.is_public == True) | (Agent.owner_user_id == user_id))  # noqa: E712
            .order_by(Agent.is_builtin.desc(), Agent.created_at.asc())
        )
        return list((await session.exec(statement)).all())

    @DaoRel
    async def list_all(self, session: AsyncSession | None = None) -> list[Agent]:
        """查询全部智能体(管理 scope)"""
        statement = select(Agent).order_by(
            Agent.is_builtin.desc(), Agent.created_at.asc()
        )
        return list((await session.exec(statement)).all())

    @DaoRel
    async def update(
        self, agent: Agent, session: AsyncSession | None = None
    ) -> Agent:
        """更新智能体字段"""
        session.add(agent)
        await session.flush()
        return agent

    @DaoRel
    async def delete(self, agent: Agent, session: AsyncSession | None = None) -> None:
        """删除智能体"""
        await session.delete(agent)
        await session.flush()
