"""问答用量服务: 回答完成后的用量落库(成本快照)与管理员统计查询。"""
import logging
from datetime import datetime

from sqlmodel import select

from common.config.db import db_rel
from common.utils.db.schema.pagination import PaginationParams, PaginationResponse
from module_ai.dao.model_config import ModelConfigDao
from module_authorization.do.user import User
from module_rag.dao.usage import ChatUsageDao
from module_rag.do.usage import ChatUsage, UsageConversationItem, UsageRecordItem
from module_rag.do.conversation import Conversation

logger = logging.getLogger(__name__)


class ChatUsageService:
    """问答用量服务"""

    def __init__(self, usage_dao: ChatUsageDao | None = None):
        self.usage_dao = usage_dao or ChatUsageDao()

    async def record(
        self,
        user_id: str,
        conversation_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        agent_id: str | None = None,
        model_id: str | None = None,
        model_name: str | None = None,
        mode: str = "",
    ) -> None:
        """
        记录一轮问答用量(成本按当次单价快照, 单价缺失记 0)

        model_id 优先: 按模型配置ID取模型标识与单价; 仅传 model_name 时
        按公共对话模型匹配。仅做旁路落库: 任何异常只告警不抛出, 不影响问答主流程。
        """
        try:
            config = None
            if model_id:
                config = await ModelConfigDao().get(model_id)
            if config is None and model_name:
                config = await ModelConfigDao().get_public_by_type_and_model(
                    "chat", model_name
                )
            if config is not None:
                model_name = config.model
            cost = self._snapshot_cost(config, prompt_tokens, completion_tokens)
            await self.usage_dao.add(
                ChatUsage(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    model_name=model_name,
                    mode=mode,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost,
                )
            )
        except Exception as e:
            logger.warning(f"记录问答用量失败 conversation={conversation_id}: {e}")

    @staticmethod
    def _snapshot_cost(config, prompt_tokens: int, completion_tokens: int) -> float:
        """按模型单价计算成本快照(元): pay_in/pay_out 口径为 元/百万token"""
        if config is None:
            return 0.0
        pay_in = float(getattr(config, "pay_in", 0.0) or 0.0)
        pay_out = float(getattr(config, "pay_out", 0.0) or 0.0)
        return round(
            prompt_tokens / 1_000_000 * pay_in + completion_tokens / 1_000_000 * pay_out,
            6,
        )

    # 非token计费能力的计价字段(与 config.dev.yaml 价格口径注释一致):
    # asr -> pay_in 元/次; tts -> pay_out 元/万字符; image -> pay_out 元/张
    _CALL_PRICE_FIELD = {"asr": "pay_in", "tts": "pay_out", "image": "pay_out"}

    async def record_call(
        self,
        user_id: str,
        kind: str,
        quantity: float = 1.0,
        model_id: str | None = None,
        model_name: str | None = None,
        conversation_id: str = "",
        agent_id: str | None = None,
    ) -> None:
        """
        记录一次非 token 计费调用(语音识别/语音合成/图像生成), mode 记能力标识

        quantity 口径: asr=调用次数(恒 1), tts=合成字符数(按万字符计价), image=生成张数。
        cost = quantity(换算后) × 对应单价; 模型未配置单价时记 0 但仍保留调用记录。
        模型解析顺序: model_id -> 公共模型匹配 -> 类型默认公共模型。
        仅做旁路落库: 任何异常只告警不抛出, 不影响主流程; 匿名调用(user_id 为空)不记录。
        """
        if not user_id:
            return
        try:
            config = None
            if model_id:
                config = await ModelConfigDao().get(model_id)
            if config is None and model_name:
                config = await ModelConfigDao().get_public_by_type_and_model(kind, model_name)
            if config is None:
                config = await ModelConfigDao().get_default_by_type(kind, active_only=True)
            if config is not None:
                model_name = config.model
            price = 0.0
            if config is not None:
                field = self._CALL_PRICE_FIELD.get(kind, "pay_in")
                price = float(getattr(config, field, 0.0) or 0.0)
            divisor = 10_000.0 if kind == "tts" else 1.0
            cost = round(quantity / divisor * price, 6)
            await self.usage_dao.add(
                ChatUsage(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                    model_name=model_name,
                    mode=kind,
                    prompt_tokens=0,
                    completion_tokens=0,
                    cost=cost,
                )
            )
        except Exception as e:
            logger.warning(f"记录 {kind} 调用用量失败: {e}")

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
