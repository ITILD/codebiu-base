"""问答用量数据访问对象(用量落库、统计聚合与分页明细)。"""
from datetime import datetime, timedelta, timezone

from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from module_ai.do.usage import ChatUsage


class ChatUsageDao:
    """问答用量数据访问对象"""

    @DaoRel
    async def add(self, usage: ChatUsage, session: AsyncSession | None = None) -> str:
        """新增一条用量记录, 返回记录ID(失败由调用方捕获, 不阻断问答主流程)"""
        session.add(usage)
        await session.flush()
        return usage.id

    @staticmethod
    def _range_start(days: int) -> datetime:
        """统计起点: 当前 UTC 时间往前 days 天(含当天)"""
        now = datetime.now(timezone.utc)
        return now - timedelta(days=days - 1)

    async def _rows(
        self,
        days: int,
        user_id: str | None,
        session: AsyncSession,
    ) -> list[ChatUsage]:
        """查询时间范围内的用量明细行(供 Python 侧聚合, 时间粒度跨库一致)"""
        stmt = select(ChatUsage).where(ChatUsage.created_at >= self._range_start(days))
        if user_id:
            stmt = stmt.where(ChatUsage.user_id == user_id)
        return (await session.exec(stmt)).all()

    @DaoRel
    async def stats(
        self,
        days: int = 30,
        user_id: str | None = None,
        top_n: int = 10,
        session: AsyncSession | None = None,
    ) -> dict:
        """
        用量统计聚合(单表内存聚合, 数据量=问答轮次, 管理页面场景可接受)

        :param days: 统计天数(含当天)
        :param user_id: 可选按用户过滤
        :param top_n: 用户排行返回条数
        """
        rows = await self._rows(days, user_id, session)

        total_prompt = total_completion = 0
        total_cost = 0.0
        conversations: set[str] = set()
        users: set[str] = set()
        daily: dict[str, dict] = {}
        by_user: dict[str, dict] = {}
        by_model: dict[str, dict] = {}

        for row in rows:
            pt, ct = row.prompt_tokens or 0, row.completion_tokens or 0
            total_prompt += pt
            total_completion += ct
            total_cost += row.cost or 0.0
            # 非对话内调用(语音/生图等) conversation_id 为空, 不计入会话数
            if row.conversation_id:
                conversations.add(row.conversation_id)
            users.add(row.user_id)

            # 按天(UTC)聚合
            day = row.created_at.strftime("%Y-%m-%d")
            d = daily.setdefault(
                day, {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "requests": 0}
            )
            d["prompt_tokens"] += pt
            d["completion_tokens"] += ct
            d["cost"] += row.cost or 0.0
            d["requests"] += 1

            # 按用户聚合
            u = by_user.setdefault(
                row.user_id,
                {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "requests": 0},
            )
            u["prompt_tokens"] += pt
            u["completion_tokens"] += ct
            u["cost"] += row.cost or 0.0
            u["requests"] += 1

            # 按模型聚合(未记录模型的归为「未记录」)
            m = by_model.setdefault(
                row.model_name or "未记录",
                {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "requests": 0},
            )
            m["prompt_tokens"] += pt
            m["completion_tokens"] += ct
            m["cost"] += row.cost or 0.0
            m["requests"] += 1

        # 补齐时间范围内的空日期, 保证趋势图连续
        daily_full: list[dict] = []
        today = datetime.now(timezone.utc).date()
        for offset in range(days - 1, -1, -1):
            key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            d = daily.get(key)
            daily_full.append(
                {
                    "date": key,
                    "prompt_tokens": d["prompt_tokens"] if d else 0,
                    "completion_tokens": d["completion_tokens"] if d else 0,
                    "cost": round(d["cost"], 6) if d else 0.0,
                    "requests": d["requests"] if d else 0,
                }
            )

        top_users = [
            {"user_id": uid, **agg}
            for uid, agg in sorted(
                by_user.items(),
                key=lambda kv: kv[1]["prompt_tokens"] + kv[1]["completion_tokens"],
                reverse=True,
            )[:top_n]
        ]
        models = [
            {"model_name": name, **agg}
            for name, agg in sorted(
                by_model.items(),
                key=lambda kv: kv[1]["prompt_tokens"] + kv[1]["completion_tokens"],
                reverse=True,
            )
        ]

        return {
            "summary": {
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_tokens": total_prompt + total_completion,
                "total_cost": round(total_cost, 6),
                "request_count": len(rows),
                "conversation_count": len(conversations),
                "active_user_count": len(users),
            },
            "daily": daily_full,
            "top_users": top_users,
            "by_model": models,
        }

    @DaoRel
    async def list_paged(
        self,
        offset: int = 0,
        limit: int = 20,
        days: int | None = None,
        user_id: str | None = None,
        model_name: str | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[list[ChatUsage], int]:
        """用量明细分页查询(时间倒序), 返回 (当前页记录, 总数)

        :param days: 可选统计天数过滤(None=不限)
        :param user_id: 可选按用户过滤
        :param model_name: 可选按模型标识模糊过滤
        """
        stmt = select(ChatUsage)
        conditions = []
        if days:
            conditions.append(ChatUsage.created_at >= self._range_start(days))
        if user_id:
            conditions.append(ChatUsage.user_id == user_id)
        if model_name:
            conditions.append(ChatUsage.model_name.like(f"%{model_name}%"))
        for cond in conditions:
            stmt = stmt.where(cond)
        count_stmt = select(func.count()).select_from(ChatUsage)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        total = (await session.exec(count_stmt)).one()
        rows = (
            await session.exec(
                stmt.order_by(ChatUsage.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
        return list(rows), int(total)

    @DaoRel
    async def conversations_agg(
        self,
        offset: int = 0,
        limit: int = 20,
        user_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[list[dict], int]:
        """对话维度用量聚合(按会话分组, 最近活跃倒序), 返回 (聚合行, 会话总数)

        聚合行含: conversation_id / user_id / rounds / prompt_tokens /
        completion_tokens / cost / last_active_at
        """
        stmt = select(
            ChatUsage.conversation_id,
            ChatUsage.user_id,
            func.count().label("rounds"),
            func.sum(ChatUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(ChatUsage.completion_tokens).label("completion_tokens"),
            func.sum(ChatUsage.cost).label("cost"),
            func.max(ChatUsage.created_at).label("last_active_at"),
        ).group_by(ChatUsage.conversation_id, ChatUsage.user_id)
        # 语音/生图等非对话内调用 conversation_id 为空, 不进入对话记录列表
        stmt = stmt.where(ChatUsage.conversation_id != "")
        if user_id:
            stmt = stmt.where(ChatUsage.user_id == user_id)
        # 总数: 按会话去重计数
        count_stmt = select(func.count(func.distinct(ChatUsage.conversation_id))).where(
            ChatUsage.conversation_id != ""
        )
        if user_id:
            count_stmt = count_stmt.where(ChatUsage.user_id == user_id)
        total = (await session.exec(count_stmt)).one()
        rows = (
            await session.exec(stmt.order_by(func.max(ChatUsage.created_at).desc()).offset(offset).limit(limit))
        ).all()
        agg = [
            {
                "conversation_id": r[0],
                "user_id": r[1],
                "rounds": r[2],
                "prompt_tokens": int(r[3] or 0),
                "completion_tokens": int(r[4] or 0),
                "cost": float(r[5] or 0.0),
                "last_active_at": r[6],
            }
            for r in rows
        ]
        return agg, int(total)

    @DaoRel
    async def last_for_conversation(
        self,
        user_id: str,
        conversation_id: str,
        session: AsyncSession | None = None,
    ) -> ChatUsage | None:
        """查询用户在指定会话的最近一条用量记录(供前端展示本轮 token/费用)"""
        stmt = (
            select(ChatUsage)
            .where(ChatUsage.user_id == user_id, ChatUsage.conversation_id == conversation_id)
            .order_by(ChatUsage.created_at.desc())
            .limit(1)
        )
        return (await session.exec(stmt)).first()
