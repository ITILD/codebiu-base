"""AI 调用用量记账服务(写入侧): 问答 token 计费与非 token 能力(asr/tts/image)计次计费。

架构说明: 记账是旁路落库(任何异常只告警不抛出, 不影响主流程);
管理端统计/明细查询在 module_rag.service.usage(需关联会话标题, 依赖方向 rag→ai 合法)。
"""
import logging

from module_ai.dao.model_config import ModelConfigDao
from module_ai.dao.usage import ChatUsageDao
from module_ai.do.usage import ChatUsage

logger = logging.getLogger(__name__)


class ChatUsageRecorder:
    """AI 调用用量记账服务(写入侧)"""

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
