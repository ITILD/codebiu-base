"""五拍协议清单投影/事件日志数据访问层(REQ-019 设计 §4.8)"""

from datetime import datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from module_agent.do.agent_plan import AgentPlanEvent, AgentPlanItem


class AgentPlanItemDao:
    @DaoRel
    async def upsert(self, item: AgentPlanItem, session: AsyncSession | None = None) -> AgentPlanItem:
        """按 (run_id, item_id) 幂等投影清单项"""
        existing = await self.get(item.run_id, item.item_id, session)
        if existing is None:
            session.add(item)
            await session.flush()
            return item
        for k in (
            "goal", "acceptance_kind", "acceptance_spec", "acceptance_hash",
            "status", "attempts", "last_reason", "verdict_passed", "verdict_reason",
        ):
            setattr(existing, k, getattr(item, k))
        session.add(existing)
        await session.flush()
        return existing

    @DaoRel
    async def get(
        self, run_id: str, item_id: str, session: AsyncSession | None = None
    ) -> AgentPlanItem | None:
        stmt = select(AgentPlanItem).where(
            AgentPlanItem.run_id == run_id, AgentPlanItem.item_id == item_id
        )
        return (await session.exec(stmt)).first()

    @DaoRel
    async def list_by_run(
        self, run_id: str, session: AsyncSession | None = None
    ) -> list[AgentPlanItem]:
        stmt = select(AgentPlanItem).where(AgentPlanItem.run_id == run_id).order_by(
            AgentPlanItem.created_at.asc()
        )
        return list((await session.exec(stmt)).all())

    @DaoRel
    async def list_by_run_ids(
        self, run_ids: list[str], session: AsyncSession | None = None
    ) -> list[AgentPlanItem]:
        """按运行实例批量取清单项(北极星项粒度聚合用, REQ-002 §7)"""
        if not run_ids:
            return []
        stmt = select(AgentPlanItem).where(AgentPlanItem.run_id.in_(run_ids))
        return list((await session.exec(stmt)).all())


class AgentPlanEventDao:
    @DaoRel
    async def add(self, event: AgentPlanEvent, session: AsyncSession | None = None) -> AgentPlanEvent:
        session.add(event)
        await session.flush()
        return event

    @DaoRel
    async def list_by_run(
        self, run_id: str, session: AsyncSession | None = None
    ) -> list[AgentPlanEvent]:
        stmt = select(AgentPlanEvent).where(AgentPlanEvent.run_id == run_id).order_by(
            AgentPlanEvent.created_at.asc()
        )
        return list((await session.exec(stmt)).all())

    @DaoRel
    async def list_finished(
        self,
        start: datetime,
        end: datetime,
        session: AsyncSession | None = None,
    ) -> list[AgentPlanEvent]:
        """时间窗内的 run 收尾事件(北极星 run 粒度聚合, REQ-002 §7.1)"""
        stmt = (
            select(AgentPlanEvent)
            .where(
                AgentPlanEvent.event_type == "run_finished",
                AgentPlanEvent.created_at >= start,
                AgentPlanEvent.created_at <= end,
            )
            .order_by(AgentPlanEvent.created_at.asc())
        )
        return list((await session.exec(stmt)).all())
