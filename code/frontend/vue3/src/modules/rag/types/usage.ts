/** 成本与用量治理: 问答 token 用量与成本统计类型(对应后端 module_rag.controller.usage) */

/** 用量汇总卡 */
export interface UsageSummary {
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  /** 成本合计(元, 按写入时单价快照累计) */
  total_cost: number
  request_count: number
  conversation_count: number
  active_user_count: number
}

/** 每日用量趋势项 */
export interface UsageDailyItem {
  date: string
  prompt_tokens: number
  completion_tokens: number
  cost: number
  requests: number
}

/** 用户用量排行项 */
export interface UsageUserItem {
  user_id: string
  username?: string | null
  nickname?: string | null
  prompt_tokens: number
  completion_tokens: number
  cost: number
  requests: number
}

/** 模型用量分布项 */
export interface UsageModelItem {
  model_name: string
  prompt_tokens: number
  completion_tokens: number
  cost: number
  requests: number
}

/** 用量统计响应 */
export interface UsageStats {
  summary: UsageSummary
  daily: UsageDailyItem[]
  top_users: UsageUserItem[]
  by_model: UsageModelItem[]
}

/** 用量明细条目(补齐用户名展示) */
export interface UsageRecordItem {
  id: string
  user_id: string
  username?: string | null
  nickname?: string | null
  conversation_id: string
  agent_id?: string | null
  model_name?: string | null
  mode: string
  prompt_tokens: number
  completion_tokens: number
  cost: number
  created_at: string
}

/** 对话维度用量聚合条目(对话记录列表) */
export interface UsageConversationItem {
  conversation_id: string
  title?: string | null
  user_id: string
  username?: string | null
  nickname?: string | null
  rounds: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  last_active_at?: string | null
}

/** 最近一轮问答用量(用户自查) */
export interface LastUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  model_name?: string | null
  mode: string
  created_at: string
}
