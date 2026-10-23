// src/modules/websearch/types/websearch.ts
// 与后端 module_websearch DO 模型一一对齐(utils/websearch/do/websearch.py)

/** 搜索引擎标识(与后端 Engine 枚举一致) */
export type Engine = 'anysearch' | 'duckduckgo' | 'tavily' | 'firecrawl';

/** 时间范围过滤(与后端 DateRange 枚举一致) */
export type DateRange = 'any' | 'day' | 'week' | 'month' | 'year';

/** 单条搜索结果(注意与 agui.ts 的 WebSearchResult 语义不同, 此为引擎原始结果) */
export interface SearchResult {
  /** 结果标题 */
  title: string;
  /** 结果链接(已清洗为真实地址) */
  url: string;
  /** 摘要描述 */
  description: string;
  /** 来源站点域名 */
  source: string;
  /** 产出该结果的引擎标识 */
  engine: Engine;
  /** 发布时间(引擎提供时才有) */
  published_date: string;
}

/** 搜索请求 */
export interface SearchRequest {
  /** 查询词(1~500 字符) */
  query: string;
  /** 引擎(为空用配置默认引擎) */
  engine?: Engine;
  /** 返回条数(1~30, 为空用配置) */
  limit?: number;
  /** 时间范围 */
  date_range?: DateRange;
}

/** 搜索响应 */
export interface SearchResponse {
  query: string;
  /** 实际使用的引擎 */
  engine: Engine;
  date_range: DateRange;
  blocked_sites: string[];
  /** 返回条数 */
  total: number;
  results: SearchResult[];
}

/** 引擎信息(GET /websearch/engines) */
export interface EngineInfo {
  /** 引擎唯一标识(请求参数 engine 用该值) */
  name: Engine;
  display_name: string;
  description: string;
  /** 是否为配置的默认引擎 */
  is_default: boolean;
  /** 是否需要 API Key */
  requires_api_key: boolean;
  /** 是否可用(API Key 已配置或无需 Key) */
  available: boolean;
}
