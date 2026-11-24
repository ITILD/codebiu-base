"""问答用量管理端查询服务(读取侧): 管理员统计/明细/对话聚合与本人最近用量。

架构说明: 用量表与写入记账在 module_ai(do/dao/service.usage, 底层能力平台);
本服务叠加知识库业务视角(会话标题关联/用户信息补齐), 依赖方向 rag→ai 合法。
"""
import logging
from sqlmodel import select

from common.config.db import db_rel
from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_authorization.do.user import User
from module_ai.dao.usage import ChatUsageDao
from module_ai.do.usage import ChatUsage, UsageConversationItem, UsageRecordItem
from module_ai.service.usage import ChatUsageRecorder
from module_rag.do.conversation import Conversation

logger = logging.getLogger(__name__)


class ChatUsageService:
    """问答用量服务(管理端查询 + 记账委托)"""

    def __init__(self, usage_dao: ChatUsageDao | None = None):
        self.usage_dao = usage_dao or ChatUsageDao()
        self._recorder = ChatUsageRecorder(self.usage_dao)

    async def record(self, *args, **kwargs) -> None:
        """记账委托(签名同 ChatUsageRecorder.record), 保持既有调用方兼容"""
        await self._recorder.record(*args, **kwargs)

    async def record_call(self, *args, **kwargs) -> None:
        """记账委托(签名同 ChatUsageRecorder.record_call), 保持既有调用方兼容"""
        await self._recorder.record_call(*args, **kwargs)

    @staticmethod
    async def _user_info_map(user_ids: list[str]) -> dict[str, tuple]:
        """批量查询用户展示信息 {user_id: (username, nickname)}"""
        ids = [uid for uid in user_ids if uid]
        if not ids:
            return {}
        async with db_rel.session_factory() as session:
            rows = (
                await session.exec(
                    select(User.id, User.username, User.nickname).where(User.id.in_(ids))
                )
            ).all()
        return {row[0]: (row[1], row[2]) for row in rows}

    async def stats(
        self, days: int = 30, user_id: str | None = None, top_n: int = 10
    ) -> dict:
        """管理员用量统计(补齐用户名/昵称展示信息)"""
        result = await self.usage_dao.stats(days, user_id, top_n)
        info = await self._user_info_map(
            [item["user_id"] for item in result.get("top_users") or []]
        )
        for item in result.get("top_users") or []:
            username, nickname = info.get(item["user_id"], (None, None))
            item["username"] = username
            item["nickname"] = nickname
        return result

    async def list_records(
        self,
        pagination: PaginationParams,
        days: int | None = None,
        user_id: str | None = None,
        model_name: str | None = None,
    ) -> PaginationResponse:
        """用量明细分页(补齐用户名/昵称)"""
        rows, total = await self.usage_dao.list_paged(
            offset=pagination.offset,
            limit=pagination.limit,
            days=days,
            user_id=user_id,
            model_name=model_name,
        )
        info = await self._user_info_map([r.user_id for r in rows])
        items = [
            UsageRecordItem(
                id=r.id,
                user_id=r.user_id,
                username=info.get(r.user_id, (None, None))[0],
                nickname=info.get(r.user_id, (None, None))[1],
                conversation_id=r.conversation_id,
                agent_id=r.agent_id,
                model_name=r.model_name,
                mode=r.mode,
                prompt_tokens=r.prompt_tokens or 0,
                completion_tokens=r.completion_tokens or 0,
                cost=r.cost or 0.0,
                created_at=r.created_at,
            )
            for r in rows
        ]
        return PaginationResponse.create(items, total, pagination)

    async def list_conversations(
        self,
        pagination: PaginationParams,
        user_id: str | None = None,
    ) -> PaginationResponse:
        """对话维度用量聚合分页(补齐会话标题与用户名/昵称)"""
        agg_rows, total = await self.usage_dao.conversations_agg(
            offset=pagination.offset,
            limit=pagination.limit,
            user_id=user_id,
        )
        # 会话标题与用户展示信息批量补齐
        titles: dict[str, str] = {}
        conv_ids = [r["conversation_id"] for r in agg_rows]
        if conv_ids:
            async with db_rel.session_factory() as session:
                c_rows = (
                    await session.exec(
                        select(Conversation.id, Conversation.title).where(
                            Conversation.id.in_(conv_ids)
                        )
                    )
                ).all()
                titles = {row[0]: row[1] for row in c_rows}
        info = await self._user_info_map([r["user_id"] for r in agg_rows])
        items = [
            UsageConversationItem(
                conversation_id=r["conversation_id"],
                title=titles.get(r["conversation_id"]),
                user_id=r["user_id"],
                username=info.get(r["user_id"], (None, None))[0],
                nickname=info.get(r["user_id"], (None, None))[1],
                rounds=r["rounds"],
                prompt_tokens=r["prompt_tokens"],
                completion_tokens=r["completion_tokens"],
                total_tokens=r["prompt_tokens"] + r["completion_tokens"],
                cost=r["cost"],
                last_active_at=r["last_active_at"],
            )
            for r in agg_rows
        ]
        return PaginationResponse.create(items, total, pagination)

    async def last_usage(self, user_id: str, conversation_id: str) -> ChatUsage | None:
        """查询用户在本会话最近一轮用量(调用方校验会话归属)"""
        return await self.usage_dao.last_for_conversation(user_id, conversation_id)
