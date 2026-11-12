// src/modules/ai/types/capability.ts
// Model 层能力注册表类型(REQ-018): static_func 代码注册表 + ai_model 三作用域解析, 双源合一视图

/** 能力注册表项(GET /ai/capabilities) */
export interface AiCapabilityItem {
  /** 能力键(Skill 的 capabilities 声明引用此键) */
  capability_key: string
  /** 供给形态: static_func(规则函数) / ai_model(大模型) / feature(环境特性) */
  kind: 'static_func' | 'ai_model' | 'feature' | 'none'
  name: string
  description: string
  /** 是否可满足 */
  available: boolean
  /** ai_model 形态: 解析到的 model_config 表 ID */
  model_config_id?: string | null
}
