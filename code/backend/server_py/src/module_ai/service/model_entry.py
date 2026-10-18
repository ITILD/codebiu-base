"""统一模型入口: 多类型模型(chat/embeddings/rerank/ocr/asr/tts)配置解析与实例构建的唯一入口

所有模型能力均通过外部服务接入, 本模块聚合此前分散在
VoiceService/OcrService/RerankService/LLMService 中的重复逻辑:

    - 配置解析(resolve_config): 显式 model_id → 显式方案 server_type → 用户个人绑定 → 全局默认
    - 实例构建(build): 按 model_type 注册表分派(chat/embeddings/rerank 走 LangChain 工厂,
      asr/tts/ocr 走在线引擎类, extra 展平为引擎配置字典)
    - 实例缓存(get_engine): 缓存键含配置 updated_at, 配置修改后自动重建, 无需手动失效
    - 缓存清理(clear_cache): 按 model_id 前缀清除(手动刷新场景, 管理接口使用)

解析优先级说明(与旧 voice 行为保持一致):
    显式指定的 model_id/server_type 优先于用户个人绑定(请求级覆盖用户偏好),
    未指定时才按 用户绑定 → 全局默认 链路解析。
"""
import json
import logging

from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_ai.dao.model_config import ModelConfigDao
from module_ai.do.model_config import ModelConfig
from module_ai.utils.llm.factory.builder import (
    build_chat_model,
    build_embeddings,
    build_rerank_model,
)
from module_ai.utils.llm.types import ModelType, ModelServerType, server_types_for
from module_ai.utils.ocr import DashscopeOCR, PaddleOCROnline
from module_ai.utils.voice.asr import OnlineASR
from module_ai.utils.voice.tts import OnlineTTS

logger = logging.getLogger(__name__)


class ModelNotConfiguredError(RuntimeError):
    """模型未配置异常(可操作): 提示用户先在模型配置中添加对应类型/方案的记录"""


def flatten_conf(config: ModelConfig | None) -> dict:
    """ModelConfig -> 引擎配置字典(asr/tts/ocr 在线引擎用)

    extra 展平为顶层键, 顶层字段回填(extra 中同名键优先):
    model/api_key/url/timeout 均为引擎所需
    """
    if config is None:
        return {}
    conf = dict(config.extra or {})
    conf.setdefault("model", config.model)
    conf.setdefault("api_key", config.api_key)
    conf.setdefault("url", config.url)
    conf.setdefault("timeout", config.timeout)
    return conf


def _build_ocr_engine(config: ModelConfig | None):
    """按 server_type/extra.protocol 构建 OCR 引擎

    - dashscope 或 extra.protocol=dashscope: 阿里云百炼方案(DashscopeOCR)
    - online(默认): PaddleOCR 官方云 API 方案(PaddleOCROnline)
    """
    conf = flatten_conf(config)
    # server_type 可能是枚举或字符串, str-mixin 枚举与 .value 直接相等比较
    if getattr(config, "server_type", None) == ModelServerType.DASHSCOPE or str(conf.get("protocol") or "") == "dashscope":
        return DashscopeOCR(conf)
    return PaddleOCROnline(conf)


class ModelEntryService:
    """统一模型入口服务: 配置解析 + 实例构建 + 缓存管理(全类型模型共用)"""

    # 实例构建注册表: model_type -> 构建函数(config, **kwargs) -> 引擎/模型实例
    # chat/embeddings/rerank 走 LangChain 工厂(按 server_type 内部分派协议);
    # asr/tts/ocr 恒为在线引擎类(协议细节由 extra 分派)
    _BUILDERS: dict[str, object] = {
        ModelType.CHAT.value: build_chat_model,
        ModelType.EMBEDDINGS.value: build_embeddings,
        ModelType.RERANK.value: build_rerank_model,
        ModelType.ASR.value: lambda config: OnlineASR(flatten_conf(config)),
        ModelType.TTS.value: lambda config: OnlineTTS(flatten_conf(config)),
        ModelType.OCR.value: lambda config: _build_ocr_engine(config),
    }

    def __init__(self, model_config_dao: ModelConfigDao | None = None):
        """依赖注入构造器: 初始化数据访问对象与实例缓存"""
        self.model_config_dao = model_config_dao or ModelConfigDao()
        # 实例缓存: "{model_type}:{config_id}:{updated_at}[:build_kwargs]" -> 引擎/模型实例
        # (多键共存: 不同用户/不同模型配置的实例可同时存活)
        self._engines: dict[str, object] = {}

    @staticmethod
    def type_key(model_type: "ModelType | str") -> str:
        """取模型类型字符串值(兼容枚举/字符串两种形态)"""
        return model_type.value if isinstance(model_type, ModelType) else str(model_type)

    def supported_server_types(self, model_type: "ModelType | str") -> list[ModelServerType]:
        """按模型类型返回可用服务方案(前后端方案选项的唯一来源)"""
        return server_types_for(model_type)

    # ---------- 配置解析 ----------

    async def _resolve_user_config(self, type_key: str, user_id: str) -> ModelConfig | None:
        """解析用户级个人绑定模型(绑定 → 默认公共模型回退链; 延迟导入避免与 module_rag 循环依赖)

        :param type_key: 模型类型字符串(chat/embeddings/rerank/asr/tts/ocr)
        :param user_id: 当前用户ID
        :return: 用户可用的模型配置; 无绑定/绑定失效且不允许回退/异常时返回 None
                 (交由调用方回落全局方案; OCR 未纳入用户绑定表, 恒走默认公共模型)
        """
        try:
            from module_rag.service.user_model import UserModelService

            resolved = await UserModelService().resolve_model(user_id, ModelType(type_key))
            if resolved.model_id is None:
                return None
            return await self.model_config_dao.get(resolved.model_id)
        except Exception as e:
            logger.warning(f"解析用户 {user_id} 的 {type_key} 模型绑定失败, 按未绑定处理: {e}")
            return None

    async def resolve_config(
        self,
        model_type: "ModelType | str",
        *,
        user_id: str | None = None,
        server_type: str | None = None,
        model_id: str | None = None,
    ) -> ModelConfig:
        """解析可用的模型配置(统一解析链, 各服务共用)

        解析优先级:
            1. model_id: 显式指定配置ID(能力测试/指定模型调用场景), 类型不匹配报错
            2. server_type: 显式指定方案(请求级覆盖用户偏好, 同旧 voice 语义)
            3. user_id: 用户个人绑定 → 默认公共模型回退链
            4. 全局默认(默认公共 > 公共 > 任意生效配置)

        :param model_type: 模型类型(chat/embeddings/rerank/ocr/asr/tts)
        :param user_id: 当前用户ID(None 按未绑定处理)
        :param server_type: 指定服务方案(如 online/dashscope)
        :param model_id: 指定模型配置ID
        :raises NotFoundError: 指定的 model_id 不存在
        :raises BusinessError: 指定的 model_id 类型不匹配
        :raises ModelNotConfiguredError: 指定方案/该类型无任何生效配置
        """
        type_key = self.type_key(model_type)
        # 1) 显式配置ID: 精确取用并校验类型
        if model_id:
            config = await self.model_config_dao.get(model_id)
            if config is None:
                raise NotFoundError(f"模型配置不存在: {model_id}")
            if self.type_key(config.model_type) != type_key:
                raise BusinessError(f"模型配置 {model_id} 不是 {type_key} 类型")
            return config
        # 2) 显式方案: 按类型 + server_type 精确匹配
        if server_type:
            config = await self.model_config_dao.get_first_by_type(type_key, server_type=server_type)
            if config is None:
                raise ModelNotConfiguredError(
                    f"未配置 {type_key} 的 {server_type} 方案: 请在模型配置中添加"
                )
            return config
        # 3) 用户个人绑定(绑定 → 默认公共模型回退链)
        if user_id:
            config = await self._resolve_user_config(type_key, user_id)
            if config is not None:
                return config
        # 4) 全局默认
        config = await self.model_config_dao.get_first_by_type(type_key)
        if config is None:
            raise ModelNotConfiguredError(
                f"未配置 {type_key} 模型: 请在模型配置中添加 model_type={type_key} 的记录"
            )
        return config

    # ---------- 实例构建与缓存 ----------

    def build(self, config: ModelConfig, **build_kwargs) -> object:
        """按配置直接构建模型/引擎实例(不走解析与缓存, 能力测试等场景用)

        :param config: 模型配置(ModelConfig 或同结构 CreateRequest 均可)
        :param build_kwargs: 构建附加参数(如 chat 的 streaming)
        :raises BusinessError: 模型类型不支持构建
        :raises ValueError: 服务方案暂未实现
        """
        type_key = self.type_key(config.model_type)
        builder = self._BUILDERS.get(type_key)
        if builder is None:
            raise BusinessError(f"暂不支持的模型类型: {type_key}")
        return builder(config, **build_kwargs)

    @staticmethod
    def _cache_key(type_key: str, config: ModelConfig, build_kwargs: dict) -> str:
        """构建缓存键: 类型 + 配置ID + updated_at(+ 构建参数), 配置变更自动失效"""
        key = f"{type_key}:{config.id}:{config.updated_at}"
        if build_kwargs:
            key += f":{json.dumps(build_kwargs, sort_keys=True, ensure_ascii=False)}"
        return key

    async def get_engine(
        self,
        model_type: "ModelType | str",
        *,
        user_id: str | None = None,
        server_type: str | None = None,
        model_id: str | None = None,
        **build_kwargs,
    ) -> object:
        """按统一解析链获取模型/引擎实例(带缓存, 配置变更自动重建)

        :param model_type: 模型类型(chat/embeddings/rerank/ocr/asr/tts)
        :param user_id: 当前用户ID(用户绑定优先于全局配置)
        :param server_type: 指定服务方案(优先于用户绑定)
        :param model_id: 指定模型配置ID(最高优先级)
        :param build_kwargs: 构建附加参数(如 chat 的 streaming, 参与缓存键)
        :return: 模型/引擎实例(类型由 model_type 决定)
        """
        type_key = self.type_key(model_type)
        config = await self.resolve_config(
            type_key, user_id=user_id, server_type=server_type, model_id=model_id
        )
        key = self._cache_key(type_key, config, build_kwargs)
        if key not in self._engines:
            self._engines[key] = self.build(config, **build_kwargs)
            logger.info("模型实例已构建: %s/%s (来源: %s)", type_key, config.server_type, key)
        return self._engines[key]

    # ---------- 缓存清理 ----------

    def clear_cache(self, model_id: str | None = None):
        """清除实例缓存

        :param model_id: 模型配置ID(前缀匹配该配置全部实例); None 时清空全部
        """
        if model_id is None:
            self._engines.clear()
            return
        # 缓存键形如 "chat:{model_id}:{updated_at}:...", 匹配第二段 model_id
        stale = [k for k in self._engines if k.split(":", 1)[-1].startswith(f"{model_id}:")]
        for key in stale:
            self._engines.pop(key, None)


# 模块级单例(全服务共用同一份实例缓存, 避免多实例重复构建)
_model_entry = ModelEntryService()


def get_model_entry() -> ModelEntryService:
    """获取统一模型入口单例"""
    return _model_entry
