// src/modules/websearch/api/websearch.ts
import { http_base_server } from '@/common/api/http';
import type { EngineInfo, SearchRequest, SearchResponse } from '../types/websearch';

/**
 * 获取搜索引擎清单(含默认标记与可用状态)
 * @returns 引擎信息列表, 未配置 Key 的引擎 available=false
 */
export const listEngines = () => {
  return http_base_server.get<EngineInfo[]>('/websearch/engines');
};

/**
 * 网页搜索(引擎为空用配置默认引擎)
 * @param request 搜索请求(查询词/引擎/条数/时间范围)
 * @returns 搜索响应(实际引擎/条数/结果列表)
 */
export const searchWeb = (request: SearchRequest) => {
  return http_base_server.post<SearchResponse>('/websearch/search', request);
};
