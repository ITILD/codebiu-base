// src/modules/agent/types/agent.ts
// 智能体模块类型定义(REQ-013): 助手 CRUD / 对话请求
// 技能清单类型(Skill Manifest 视图)见 ./skill.ts(REQ-018 起旧 name/display_name/capability 契约已下线)

/** 对话模式运行参数(内置于智能体 chat_modes) */
export interface ChatModeConfig {
  think_level?: 'off' | 'low' | 'high'
  search_rounds?: number
  max_loops?: number
  max_model_calls?: number
  max_tool_calls?: number
  wall_clock_s?: number
}

/** 智能体(助手)信息 */
export interface AgentInfo {
  id: string
  name: string
  description: string
  /** 默认系统提示词(空串走内置默认) */
  default_prompt: string
  /** 默认关联知识库(项目)ID列表, 供知识库问答技能回退 */
  default_project_ids: string[]
  /** 技能名单(须全部在后端注册表内) */
  skills: string[]
  owner_user_id: string
  is_public: boolean
  is_builtin: boolean
  /** 执行策略 direct/react/plan_execute */
  execution_strategy?: string | null
  /** 对话模式配置 {模式名: 运行参数} */
  chat_modes?: Record<string, ChatModeConfig> | null
  created_at: string
  updated_at: string
}

/** 创建智能体请求 */
export interface AgentCreateReq {  name: string
  description?: string
  default_prompt?: string
  default_project_ids?: string[]
  skills?: string[]
  is_public?: boolean
}

/** 更新智能体请求(全字段可选) */
export interface AgentUpdateReq {
  name?: string
  description?: string
  default_prompt?: string
  default_project_ids?: string[]
  skills?: string[]
  is_public?: boolean
  execution_strategy?: string | null
  chat_modes?: Record<string, ChatModeConfig> | null
}

/** 智能体对话请求(SSE) */
export interface AgentChatReq {
  message: string
  /** 智能体ID(空则用会话绑定的) */
  agent_id?: string
}

/** 任务清单投影项(agent_plan_item, 断线兜底/历史回放用, REQ-002 §6.3) */
export interface AgentPlanProjectionItem {  run_id: string
  item_id: string
  goal: string
  acceptance_kind: string
  acceptance_spec: string
  acceptance_hash: string
  status: string
  attempts: number
  last_reason: string
  verdict_passed: boolean | null
  verdict_reason: string | null
  created_at: string
  updated_at: string
}

/** 北极星指标(REQ-002 §7.1: 三项北极星 + 两项下钻) */
export interface NorthStarMetrics {
  /** 假完成率(不变量监控: done 但验收未通过, 正常恒为 0) */
  fake_done_rate: number
  /** 任务成功率(run 粒度) */
  success_rate: number
  /** 每成功任务平均成本 */
  cost_per_success: {
    tokens: number
    tool_calls: number
    elapsed_ms: number
  }
  drilldown: {
    /** 首次交卷通过率 */
    first_submit_pass_rate: number
    /** 预算触顶率 */
    budget_hit_rate: number
  }
  runs: number
  items: number
  window: { start: string; end: string }
  agent_key: string | null
}
