"""重排序服务: 按模型配置(model_config 表 model_type=rerank)执行重排序

配置解析/引擎构建/缓存统一委托 ModelEntryService(service/model_entry.py 统一入口):
    - model_type=rerank + server_type=dashscope/ollama/vllm/openai 的记录即为可选方案
    - model_id 参数可选: 指定时精确匹配, 缺省按 用户绑定 → 全局默认 解析
    - 引擎缓存键含配置 updated_at, 配置修改后自动重建
"""
import logging
import time

from common.utils.fastapi_ex.exceptions import BusinessError
from module_ai.do.rerank import RerankRequest, RerankResponse
from module_ai.service.model_entry import ModelEntryService, ModelNotConfiguredError, get_model_entry
from module_ai.utils.llm.rerank.interface import Rerank

logger = logging.getLogger(__name__)

# 单文档文本截断上限(超长文档重排序意义有限且耗费 token)
_MAX_DOC_CHARS = 4000


class RerankService:
    """重排序服务门面: 引擎解析/构建/缓存委托统一模型入口, 本层聚焦排序业务"""

    def __init__(self, model_entry: ModelEntryService | None = None):
        """依赖注入构造器: 统一入口缺省取全局单例"""
        self._entry = model_entry or get_model_entry()

    async def get_reranker(self, model_id: str | None = None) -> Rerank:
        """获取重排序引擎(指定 model_id 或按 用户绑定/全局配置 自动选择)

        :param model_id: 模型配置ID(None 时自动选择)
        :raises NotFoundError: 指定的模型配置不存在
        :raises BusinessError: 配置类型不匹配 / 未配置 rerank 模型 / 方案不支持
        """
        try:
            # 构建失败(ValueError: 方案不支持/分数范围非法)与未配置统一转 BusinessError 保持接口错误语义
            return await self._entry.get_engine("rerank", model_id=model_id)  # type: ignore[return-value]
        except ModelNotConfiguredError as e:
            raise BusinessError(str(e))
        except ValueError as e:
            raise BusinessError(str(e))

    async def rerank(self, request: RerankRequest) -> RerankResponse:
        """执行重排序: 返回按相关性降序的 [{node, relevance_score}] 列表

        :param request: 重排序请求(query + documents)
        :return: 排序结果(node 保留原文档对象)
        """
        start = time.time()
        reranker = await self.get_reranker(request.model_id)

        # 提取待排序文本(字典按 sort_key 取值, 超长截断)
        docs = request.documents
        texts = [
            (doc if isinstance(doc, str) else str(doc.get(request.sort_key, "")))[
                :_MAX_DOC_CHARS
            ]
            for doc in docs
        ]
        if not texts:
            return RerankResponse(results=[], elapsed=round(time.time() - start, 3))

        ranked = await reranker.arerank(request.query, texts, request.top_n)
        # 按返回索引映射回原文档
        results = [
            {
                "node": docs[item["index"]],
                "relevance_score": float(
                    item.get("relevance_score", item.get("score", 0.0))
                ),
            }
            for item in ranked
            if isinstance(item, dict) and item.get("index") is not None
        ]
        return RerankResponse(results=results, elapsed=round(time.time() - start, 3))
