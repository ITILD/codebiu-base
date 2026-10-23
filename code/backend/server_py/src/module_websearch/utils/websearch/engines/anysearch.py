"""
AnySearch 搜索引擎实现(免 Key 可用的 AI 搜索 API)

POST {api_base}/v1/search, 请求体 {"query", "tag", "params"}。
- 免费额度无需 API Key(不带 Authorization 头即可; 注意空 Bearer 反而 401, 故 Key 为空时不携带)
- 配置 api_key 后享更高额度, 以 Bearer 方式携带
- tag 为搜索场景标签(如 code.doc), 默认取配置 default_tag, 为空不传
- 不支持服务端屏蔽站点/时间范围, 统一在本地过滤; 条数由本地截断
响应: {"code":0, "data":{"results":[{title,url,snippet,content}]}}
"""
import logging

from module_websearch.config.settings import get_websearch_settings
from module_websearch.utils.websearch.base import JSON_HEADERS, SearchEngine
from module_websearch.utils.websearch.do.websearch import DateRange, Engine, SearchResult

logger = logging.getLogger(__name__)

SEARCH_PATH = "/v1/search"


class AnySearchEngine(SearchEngine):
    """AnySearch 引擎(免 Key 可用, 配置 Key 获更高额度)"""

    name = Engine.ANYSEARCH
    display_name = "AnySearch"
    description = "AI 搜索 API,免 Key 可用免费额度,配置 API Key 后享更高额度"
    requires_api_key = False

    async def is_configured(self) -> bool:
        """免 Key 引擎恒可用(Key 仅用于提升额度)"""
        return True

    async def search(
        self,
        query: str,
        limit: int,
        date_range: DateRange = DateRange.ANY,
        blocked_sites: list[str] | None = None,
    ) -> list[SearchResult]:
        """
        执行 AnySearch 搜索
        :param query: 查询信息(句子或关键词)
        :param limit: 返回条数上限(服务端不感知, 本地截断)
        :param date_range: 时间范围限制(API 不支持, 忽略)
        :param blocked_sites: 屏蔽的站点域名列表(API 不支持, 本地过滤)
        :return: 搜索结果列表
        """
        ws = await get_websearch_settings()
        api_key = ws.anysearch.api_key
        headers = dict(JSON_HEADERS)
        # Key 为空时省略 Authorization 头(实测空 Bearer 会 401), 有 Key 时 Bearer 携带
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload: dict = {"query": query, "params": {}}
        tag = (ws.anysearch.default_tag or "").strip()
        if tag:
            payload["tag"] = tag

        url = ws.anysearch.api_base.rstrip("/") + SEARCH_PATH
        async with self.build_client(headers=headers, timeout=ws.timeout, proxy=ws.proxy) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        data = response.json()
        # 兼容 {"code":0,"data":{...}} 包装与裸 results 两种形态
        body = data.get("data") if isinstance(data.get("data"), dict) else data
        results: list[SearchResult] = []
        for item in body.get("results") or []:
            link = str(item.get("url") or "")
            title = str(item.get("title") or "").strip()
            if not link or not title:
                continue
            # snippet 为摘要, content 为长文; 优先 snippet, 缺失时截取 content 前 500 字符
            description = str(item.get("snippet") or "").strip()
            if not description:
                description = str(item.get("content") or "").strip()[:500]
            results.append(
                SearchResult(
                    title=title,
                    url=link,
                    description=description,
                    source=self.host_of(link),
                    engine=self.name,
                    published_date=str(item.get("published_date") or ""),
                )
            )
        return self.filter_blocked(results, blocked_sites)[:limit]


if __name__ == "__main__":
    # 简单自测: python -m module_websearch.utils.websearch.engines.anysearch "查询词"
    import asyncio
    import sys

    test_query = sys.argv[1] if len(sys.argv) > 1 else "fastapi"
    print(asyncio.run(AnySearchEngine().search(test_query, 5)))
