// 操作审计日志类型(REQ-009, 对应后端 /audit_logs)
export interface AuditLog {
  id: string
  /** 操作用户ID(匿名请求为空) */
  user_id: string | null
  /** 操作用户名(登录请求取表单用户名) */
  username: string | null
  method: string
  path: string
  /** 请求参数摘要(敏感字段已脱敏) */
  params_digest: string | null
  status_code: number
  /** 耗时(毫秒) */
  duration_ms: number
  ip: string | null
  user_agent: string | null
  created_at: string
}
