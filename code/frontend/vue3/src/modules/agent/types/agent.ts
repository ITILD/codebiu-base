// src/modules/agent/types/agent.ts
// 智能体模块类型定义(REQ-013): 助手 CRUD / 技能清单 / 对话请求

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
  created_at: string
  updated_at: string
}

/** 技能注册表清单项 */
export interface SkillInfo {
  name: string
  display_name: string
  description: string
  capability: 'read' | 'write'
}

/** 创建智能体请求 */
export interface AgentCreateReq {
  name: string
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
}

/** 智能体对话请求(SSE) */
export interface AgentChatReq {
  message: string
  /** 智能体ID(空则用会话绑定的) */
  agent_id?: string
}
