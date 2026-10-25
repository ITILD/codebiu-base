"""模型配置服务: 配置 CRUD/校验 + 统一模型入口(解析/构建/缓存)

本文件聚合模型配置线与统一模型入口 ModelEntryService:
按 显式配置 → 显式方案 → 用户绑定 → 全局默认 解析配置, 再按 model_type
分派构建在线引擎/LangChain 模型, 配置变更(updated_at 变化)自动失效缓存。
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from common.utils.db.schema.pagination import InfiniteScrollParams, InfiniteScrollResponse, PaginationParams, PaginationResponse
from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_ai.dao.model_config import ModelConfigDao
from module_ai.do.capability import ModelTypeEnum
from module_ai.do.model_config import (
    ModelConfig,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelScope,
)
from module_ai.utils.llm.factory.builder import (
    build_chat_model,
    build_embeddings,
    build_image_model,
    build_rerank_model,
)
from module_ai.utils.llm.types import ModelServerType, ModelType, server_types_for
from module_ai.utils.ocr import DashscopeOCR, PaddleOCROnline
from module_ai.utils.voice.asr import OnlineASR
from module_ai.utils.voice.tts import OnlineTTS

logger = logging.getLogger(__name__)

# url 协议白名单: http/https 为常规 API 端点; ws/wss 为语音流式(ASR/TTS 实时 WS)端点
_ALLOWED_URL_SCHEMES = ("http://", "https://", "ws://", "wss://")


class ModelConfigService:
    """模型配置服务层"""

    def __init__(self, model_config_dao: ModelConfigDao =None):
        """依赖注入构造器:初始化所需的数据访问对象"""
        self.model_config_dao = model_config_dao or ModelConfigDao()
        # 后台校验任务引用集(防止任务被 GC, 完成后自动移除)
        self._check_tasks: set[asyncio.Task] = set()

    @staticmethod
    def _validate_url(url: str | None) -> None:
        """
        校验 base_url 协议白名单(http/https) + 可选域名黑名单(配置 model_url_domain_blacklist)
        :param url: API基础URL(None/空 跳过)
        :raises ValueError: 协议非法或命中黑名单域名
        """
        if not url:
            return
        lowered = url.strip().lower()
        if not lowered.startswith(_ALLOWED_URL_SCHEMES):
            raise ValueError(f"模型 url 仅支持 http/https 协议: {url}")
        # 可选域名黑名单(走配置节, 未配置则不启用)
        try:
            from common.config.index import conf
            if "model_url_domain_blacklist" in conf:
                blacklist = [str(d).lower() for d in conf.model_url_domain_blacklist]
                if any(d in lowered for d in blacklist if d):
                    raise ValueError(f"模型 url 命中禁用域名: {url}")
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"读取模型 url 域名黑名单配置失败, 跳过校验: {e}")

    @staticmethod
    def _log_write_audit(action: str, config: ModelConfigCreate | ModelConfig | None = None) -> None:
        """模型配置写操作审计日志(logging 起步; 私有/部门模型记录归属与去向)"""
        if config is None:
            return
        scope = getattr(config, "scope", None)
        if scope == ModelScope.PUBLIC:
            return  # 公共模型由管理员维护, 无需逐条审计
        logger.info(
            f"[模型审计] {action} scope={scope} "
            f"model={getattr(config, 'model', None)} "
            f"owner={getattr(config, 'user_id', None)} dept={getattr(config, 'dept_id', None)}"
        )

    async def _ensure_default_unique(
        self,
        model_type: str,
        current_id: str | None = None,
    ) -> None:
        """
        保证该模型类型的默认公共模型唯一: 若存在旧的默认模型且不是当前记录, 取消其默认标记
        :param model_type: 模型类型
        :param current_id: 当前操作的模型ID(更新时排除自身)
        """
        current = await self.model_config_dao.get_default_by_type(model_type)
        if current is not None and current.id != current_id:
            await self.model_config_dao.update(current.id, ModelConfigUpdate(is_default=False))

    def _normalize_scope(self, model_config: ModelConfigCreate | ModelConfigUpdate) -> None:
        """scope 与 dept_id/is_default 一致性校验与规整"""
        scope = model_config.scope
        # 部门模型必须有归属部门
        if scope == ModelScope.DEPT:
            if not getattr(model_config, "dept_id", None):
                raise ValueError("部门模型必须指定归属部门(dept_id)")
        elif scope is not None:
            # 个人/公共模型不携带部门
            model_config.dept_id = None
        # 默认公共模型标记仅对 public 生效
        if getattr(model_config, "is_default", False) and scope != ModelScope.PUBLIC:
            model_config.dept_id = None

    async def add(self, model_config: ModelConfigCreate) -> str:
        """
        添加新的模型配置(允许同名,以来源/配置区分)
        校验 base_url 协议白名单; 私有/部门模型写操作记审计日志
        :param model_config: 模型配置数据
        :return: 创建的模型配置ID
        """
        self._normalize_scope(model_config)
        self._validate_url(model_config.url)
        # 设置默认公共模型时, 先取消该类型旧的默认标记, 保证唯一
        if model_config.scope == ModelScope.PUBLIC and model_config.is_default:
            await self._ensure_default_unique(model_config.model_type.value)
        model_id = await self.model_config_dao.add(model_config)
        self._log_write_audit("create", model_config)
        # 写库后后台自动校验并回写结果(check_valid/check_format/checked_at)
        self._schedule_check(model_id)
        return model_id

    async def delete(self, id: str):
        """
        删除模型配置
        :param id: 模型配置ID
        """
        existing = await self.model_config_dao.get(id)
        await self.model_config_dao.delete(id)
        self._log_write_audit("delete", existing)

    async def update(self, model_config_id: str, model_config: ModelConfigUpdate):
        """
        更新模型配置
        url/api_key 为空值(None/空串)时跳过更新, 防止前端携带脱敏后的空值覆盖真实密钥;
        校验 base_url 协议白名单; 私有/部门模型写操作记审计日志
        :param model_config_id: 模型配置ID
        :param model_config: 模型配置更新数据
        """
        # 空值保护: 前端编辑被脱敏的模型时 url/api_key 会以空值回传, 不覆盖真实值
        update_data = model_config.model_dump(exclude_unset=True)
        update_data = {
            k: v
            for k, v in update_data.items()
            if not (k in ("url", "api_key") and not v)
        }
        scope = update_data.get("scope") if "scope" in update_data else None
        if scope is not None:
            if scope == ModelScope.DEPT and not update_data.get("dept_id"):
                # 更新时若切换为部门但未带部门, 回填当前已存部门
                existing = await self.model_config_dao.get(model_config_id)
                if existing and existing.scope == ModelScope.DEPT:
                    update_data["dept_id"] = existing.dept_id
                elif existing and not update_data.get("dept_id"):
                    update_data["dept_id"] = None
            elif scope != ModelScope.DEPT:
                update_data["dept_id"] = None
        # 默认公共模型唯一性
        if update_data.get("is_default") is True and (
            scope == ModelScope.PUBLIC
            or ("scope" not in update_data and await self._becomes_public_default(model_config_id))
        ):
            existing = await self.model_config_dao.get(model_config_id)
            if existing:
                # model_type 未随本次提交时回退库中已有类型(避免 KeyError)
                model_type = update_data.get("model_type", existing.model_type)
                await self._ensure_default_unique(
                    model_type.value if hasattr(model_type, "value") else model_type,
                    current_id=model_config_id,
                )
        if "url" in update_data:
            self._validate_url(update_data["url"])
        if update_data:
            normalized = ModelConfigUpdate(**update_data)
            await self.model_config_dao.update(model_config_id, normalized)
            # 配置变更后重新校验并回写结果
            self._schedule_check(model_config_id)
        # 审计: 以更新后完整记录为准
        self._log_write_audit("update", await self.model_config_dao.get(model_config_id))

    def _schedule_check(self, model_config_id: str) -> None:
        """调度后台连通性校验任务(不阻塞保存接口, 结果回写后前端展示能力标签)"""
        task = asyncio.create_task(self._check_and_persist(model_config_id))
        # 持有任务引用防止被 GC, 完成后自动移除
        self._check_tasks.add(task)
        task.add_done_callback(self._check_tasks.discard)

    async def _check_and_persist(self, model_config_id: str) -> None:
        """后台校验模型配置并把结果回写(check_valid/check_format/checked_at/check_result)"""
        try:
            config = await self.model_config_dao.get(model_config_id)
            if config is None:
                return
            # 仅自动校验文本类模型(ocr/asr/tts 本地语音类暂无在线测试)
            type_key = (
                config.model_type.value
                if hasattr(config.model_type, "value")
                else str(config.model_type)
            )
            if type_key not in (ModelType.CHAT.value, ModelType.EMBEDDINGS.value, ModelType.RERANK.value):
                return
            # 延迟导入避免与 LLMService 循环依赖
            from module_ai.service.llm import LLMService

            llm_service = LLMService()
            items = await llm_service.run_capability_tests(config)
            by_cap = {item.capability: item for item in items}
            now = datetime.now(timezone.utc)
            # 由能力测试结果推导旧校验字段(check_valid/check_format)
            is_valid: bool | None = None
            is_format: bool | None = None
            if type_key == ModelType.CHAT.value and "chat" in by_cap:
                is_valid = by_cap["chat"].ok
                is_format = by_cap["structured"].ok
            elif type_key == ModelType.EMBEDDINGS.value and "embedding" in by_cap:
                is_valid = by_cap["embedding"].ok
            elif type_key == ModelType.RERANK.value and "rerank" in by_cap:
                is_valid = by_cap["rerank"].ok
            check_result = {
                item.capability: {
                    "capability": item.capability,
                    "label": item.label,
                    "ok": item.ok,
                    "detail": item.detail,
                    "error": item.error,
                    "elapsed": item.elapsed,
                    "checked_at": now.isoformat(),
                }
                for item in items
            }
            await self.model_config_dao.update(
                model_config_id,
                ModelConfigUpdate(
                    check_valid=is_valid,
                    check_format=is_format if type_key == ModelType.CHAT.value else None,
                    check_result=check_result or None,
                    checked_at=now,
                ),
            )
            logger.info(
                f"模型配置后台校验完成: {config.model} valid={is_valid} format={is_format} "
                f"caps={ {c: i['ok'] for c, i in check_result.items()} }"
            )
        except Exception as e:
            logger.warning(f"模型配置后台校验失败[{model_config_id}]: {e}")

    async def persist_check_result(self, model_config_id: str, check_result: dict) -> None:
        """仅回写能力测试明细(直连 DAO, 不走 update 流程避免重复触发自动校验)"""
        await self.model_config_dao.update(
            model_config_id,
            ModelConfigUpdate(check_result=check_result),
        )

    async def _becomes_public_default(self, model_config_id: str) -> bool:
        """更新未显式改 scope 时, 判断是否仍为 public 且当前即为默认"""
        existing = await self.model_config_dao.get(model_config_id)
        if existing is None:
            return False
        return existing.scope == ModelScope.PUBLIC

    async def get(self, id: str) -> ModelConfig | None:
        """
        获取单个模型配置
        :param id: 模型配置ID
        :return: 模型配置对象
        """
        return await self.model_config_dao.get(id)


    async def list_paged(
        self,
        pagination: PaginationParams,
        model: str | None = None,
        model_type: str | None = None,
        server_type: str | None = None,
        user_id: str | None = None,
        dept_id: str | None = None,
        is_admin: bool = False,
        scope: str | None = None,
        filter_user_ids: list[str] | None = None,
    ) -> PaginationResponse:
        """
        分页获取模型配置列表(支持多字段过滤 + 当前用户可见性)
        :param pagination: 分页参数
        :param model: 模型标识名称模糊匹配
        :param model_type: 模型类型精确过滤
        :param server_type: 服务类型精确过滤
        :param user_id: 当前用户ID(可见性: 本人模型)
        :param dept_id: 当前用户部门ID(可见性: 部门模型)
        :param is_admin: 管理员可见全部
        :param scope: 归属范围过滤
        :param filter_user_ids: 按所有者ID列表过滤(管理员按用户名检索场景)
        :return: 分页响应数据
        """
        items = await self.model_config_dao.list_paged(
            pagination,
            model=model,
            model_type=model_type,
            server_type=server_type,
            user_id=user_id,
            dept_id=dept_id,
            is_admin=is_admin,
            scope=scope,
            filter_user_ids=filter_user_ids,
        )
        total = await self.model_config_dao.count(
            model=model,
            model_type=model_type,
            server_type=server_type,
            user_id=user_id,
            dept_id=dept_id,
            is_admin=is_admin,
            scope=scope,
            filter_user_ids=filter_user_ids,
        )
        return PaginationResponse.create(items, total, pagination)

    def mask_secrets(
        self, configs: ModelConfig | list[ModelConfig] | None, user_id: str, is_admin: bool = False
    ) -> None:
        """
        敏感信息脱敏(就地修改):
        - 全局管理员: 后台运维需要账号/密码明文(url/api_key), 一律不脱敏
        - 其他用户: 仅本人私有模型(scope=user 且 user_id==本人)保留明文,
          公共/部门/他人私有一律脱敏(v4 4.1/4.2)
        :param configs: 单个或多个模型配置对象(None 忽略)
        :param user_id: 当前用户ID
        :param is_admin: 全局管理员豁免脱敏(可见全部 url/api_key 明文)
        """
        if configs is None or is_admin:
            return
        items = configs if isinstance(configs, list) else [configs]
        for config in items:
            if config is None:
                continue
            is_owner_private = (
                config.scope == ModelScope.USER and config.user_id == user_id
            )
            if not is_owner_private:
                config.url = None
                config.api_key = None

    async def get_scroll(
        self,
        params: InfiniteScrollParams,
        user_id: str | None = None,
        dept_id: str | None = None,
        is_admin: bool = False,
    ) -> InfiniteScrollResponse:
        """
        滚动加载模型配置列表(带可见性过滤)
        :param params: 滚动参数
        :param user_id/dept_id/is_admin: 见 list_paged
        :return: 滚动响应数据
        """
        items = await self.model_config_dao.get_scroll(
            params, user_id=user_id, dept_id=dept_id, is_admin=is_admin
        )
        return InfiniteScrollResponse.create(items, params.limit)
    
    async def get_default_params(self, model_name: str) -> dict:
        """
        获取指定模型的默认参数kv(基于 ModelConfig 字段默认值)
        :param model_name: 模型标识名称
        :return: 默认参数kv字典
        """
        from pydantic_core import PydanticUndefined

        from module_ai.utils.llm.factory.config import ModelConfig

        return {
            name: (info.default if info.default is not PydanticUndefined else None)
            for name, info in ModelConfig.model_fields.items()
            if name != "model"  # model 为调用方传入的标识名称, 不在默认参数内
        }
    

class ModelNotConfiguredError(RuntimeError):
    """模型未配置异常(可操作): 提示用户先在模型配置中添加对应类型/方案的记录"""


@runtime_checkable
class ModelResolver(Protocol):
    """模型解析能力契约: 按用户绑定/全局默认解析可用模型配置"""

    async def resolve_model_id(
        self, model_type: ModelTypeEnum | str, user_id: str | None = None
    ) -> str | None:
        """返回可用模型配置ID; 未配置时返回 None, 由调用方给出可操作提示"""
        ...


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
    # chat/embeddings/rerank/image 走工厂(按 server_type 内部分派协议);
    # asr/tts/ocr 恒为在线引擎类(协议细节由 extra 分派)
    _BUILDERS: dict[str, object] = {
        ModelType.CHAT.value: build_chat_model,
        ModelType.EMBEDDINGS.value: build_embeddings,
        ModelType.RERANK.value: build_rerank_model,
        ModelType.IMAGE.value: build_image_model,
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


if __name__ == "__main__":
    import asyncio
    from common.config.index import conf
    model_config_service = ModelConfigService()
    async def main():
        model_conf = conf.ai.aliyun.chat_mini
        # 添加一份
        model_obj = ModelConfigCreate(**model_conf.to_dict())
        await model_config_service.add(model_obj)
        pass
    asyncio.run(main())