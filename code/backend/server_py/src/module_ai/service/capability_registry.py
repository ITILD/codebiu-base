"""Model 层能力注册与解析(REQ-018): ai_model + static_func 双源合一

能力解析入口唯一: capability_registry.resolve(capability_key, ctx) ——
Skill 声明能力键, 运行时经此处解析到具体供给(大模型 / 规则函数 / 环境特性),
Skill 实现不感知差异(设计 §2.2 平权原则)。

解析顺序: static_func 代码注册表 → ai_model(model_config 表, 按 model_type 与
三作用域解析链) → 环境特性提供器(如 store:bm25, 由领域模块注册探测函数)。
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 环境特性提供器: 前缀(如 "store") → 异步探测函数(suffix, user_id) -> bool
# 领域模块启动时注册(如 module_rag 注册向量存储能力探测), 不在契约层硬编码
FeatureProbe = Callable[[str, str | None], Awaitable[bool]]
_FEATURE_PROVIDERS: dict[str, FeatureProbe] = {}


class ResolvedCapability(BaseModel):
    """单能力解析结果(三种供给形态分叉, 见设计 §2.2 契约分叉表)"""

    capability_key: str
    kind: str = Field(description="供给形态: ai_model / static_func / feature / none")
    available: bool = Field(description="是否可满足")
    model_config_id: str | None = Field(default=None, description="ai_model: model_config 表 ID")
    model_type: str | None = Field(default=None, description="ai_model: 模型类型")
    static_func_key: str | None = Field(default=None, description="static_func: 注册表键")


def register_feature_provider(prefix: str, probe: FeatureProbe) -> None:
    """注册环境特性探测器(如 prefix="store", 键 "store:bm25" → probe("bm25", user_id))

    由领域模块在模块装配时调用; 重复注册以后注册者为准(测试可覆盖)
    """
    _FEATURE_PROVIDERS[prefix] = probe


async def resolve(capability_key: str, user_id: str | None = None) -> ResolvedCapability:
    """解析能力键到具体供给(入口唯一)

    :param capability_key: 能力键: static_func 键 / model_type 名(chat/embeddings/...) /
        环境特性键(前缀:特性, 如 store:bm25)
    :param user_id: 当前用户(ai_model 三作用域解析链用)
    """
    from module_ai.functions import get_static_func

    # 1) static_func 代码注册表(零模型路线)
    fn = get_static_func(capability_key)
    if fn is not None:
        return ResolvedCapability(
            capability_key=capability_key, kind="static_func",
            available=True, static_func_key=fn.key,
        )

    # 2) 环境特性(前缀:特性)
    if ":" in capability_key:
        prefix, _, suffix = capability_key.partition(":")
        probe = _FEATURE_PROVIDERS.get(prefix)
        if probe is not None:
            try:
                ok = bool(await probe(suffix, user_id))
            except Exception as e:  # 探测异常按不可满足处理(不阻断解析链)
                logger.warning("特性探测失败 %s: %s", capability_key, e)
                ok = False
            return ResolvedCapability(
                capability_key=capability_key, kind="feature", available=ok,
            )

    # 3) ai_model: 按 model_type 走三作用域解析链(用户绑定→部门→公共默认→任意公共)
    try:
        from module_ai.service.model_config import ModelEntryService

        resolved = await ModelEntryService().resolve_config(capability_key, user_id=user_id)
    except Exception as e:
        logger.debug("ai_model 能力解析失败 %s: %s", capability_key, e)
        resolved = None
    if resolved is not None:
        return ResolvedCapability(
            capability_key=capability_key, kind="ai_model", available=True,
            model_config_id=getattr(resolved, "config_id", None)
            or getattr(resolved, "model_id", None)
            or getattr(resolved, "id", None),
            model_type=capability_key,
        )

    return ResolvedCapability(capability_key=capability_key, kind="none", available=False)


async def list_capabilities(user_id: str | None = None) -> list[dict[str, Any]]:
    """能力注册表合一视图(GET /ai/capabilities): static_func + 可见 ai_model 默认项"""
    from module_ai.functions import list_static_funcs

    items: list[dict[str, Any]] = [
        {
            "capability_key": f.key,
            "kind": "static_func",
            "name": f.name,
            "description": f.description,
            "available": True,
        }
        for f in list_static_funcs()
    ]
    # ai_model 侧: 各 model_type 是否有可解析供给(不罗列具体配置, 配置管理在模型管理页)
    for model_type in ("chat", "embeddings", "rerank", "ocr", "asr", "tts"):
        resolved = await resolve(model_type, user_id)
        items.append(
            {
                "capability_key": model_type,
                "kind": "ai_model",
                "name": model_type,
                "description": f"大模型能力({model_type}), 经模型配置三作用域解析",
                "available": resolved.available,
                "model_config_id": resolved.model_config_id,
            }
        )
    return items
