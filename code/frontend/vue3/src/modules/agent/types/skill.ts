// src/modules/agent/types/skill.ts
// 能力平台类型定义(REQ-018): Skill Manifest 视图 / 统一调用信封 / 调用观测 / job 编排 / 自定义 prompt Skill

import type { PaginationParams } from '@/common/types/common'

/** JSON Schema 属性项(input_schema.properties 值, 调试表单按此动态渲染) */
export interface SchemaProperty {
  type?: string
  title?: string
  description?: string
  default?: unknown
  enum?: unknown[]
  [key: string]: unknown
}

/** Skill Manifest 视图项(GET /agent/skills) */
export interface SkillInfo {
  /** 全局键 {namespace}.{key}(如 sys.doc_parse) */
  key: string
  /** 展示名称 */
  name: string
  description: string
  /** 业务分类: ingest/retrieval/generation/governance/action */
  category: string
  /** 实现类型: builtin_tool/prompt/python_script/script/mcp_tool */
  skill_type: string
  /** 能力来源: static(零模型)/ai(必需模型)/hybrid(可降级) */
  nature: 'static' | 'ai' | 'hybrid'
  version: string
  /** 副作用声明: none/read/write/external */
  side_effects: string
  /** 是否暴露给智能体 tool-calling */
  agent_callable: boolean
  /** 能力需求: 必需(缺失即失败)/可选(缺失降级)/能力组(组间任一可满足) */
  capabilities: {
    required: string[]
    optional: string[]
    alternatives: string[][]
  }
  /** 执行形态声明 */
  execution: {
    modes: string[]
    inline_timeout_s: number
    queued_timeout_s: number
    resource_domain: string
    inline_max_input_bytes: number | null
  }
  input_schema: {
    type?: string
    required?: string[]
    properties?: Record<string, SchemaProperty>
    [key: string]: unknown
  }
  output_schema: Record<string, unknown>
}

/** Skill 调用统一信封(POST /agent/skills/{key}/invoke 返回) */
export interface SkillInvokeEnvelope {
  invocation_id: string
  skill_key: string
  mode: string
  status: string
  task_id: string | null
  result: Record<string, unknown> | null
  error: { class: string; message: string } | null
  progress: number
  degraded: boolean
}

/** 调用记录列表项(GET /agent/invocations) */
export interface InvocationItem {
  invocation_id: string
  skill_key: string
  mode: string
  status: string
  degraded: boolean
  error_class: string | null
  duration_ms: number | null
  task_id: string | null
  /** 触发入口: web/agent/task/debug */
  entry: string | null
  created_at: string
}

/** 调用记录详情(GET /agent/invocations/{id}, 大字段截断后的观测口径) */
export interface InvocationDetail extends InvocationItem {
  skill_version: string | null
  priority_class: string | null
  idempotency_key: string | null
  input_summary: Record<string, unknown> | null
  output: Record<string, unknown> | null
  error_message: string | null
  tokens: number | null
  started_at: string | null
  finished_at: string | null
}

/** 调用记录列表查询参数(与后端过滤参数对齐) */
export type InvocationListParams = PaginationParams & {
  skill_key?: string
  status_filter?: string
}

/** job 步骤声明(GET /agent/jobs 的 steps 项) */
export interface AgentStepDef {
  id: string
  /** 调用的 Skill 全局键 */
  skill: string
  /** 展开字段名(None 单项调用) */
  fan_out: string | null
  item_key: string
  depends_on: string[]
  /** 步骤级准入表达式(False 整步跳过) */
  when: string | null
  /** 展开项级过滤表达式(True 该项跳过) */
  skip_if: string | null
  consume: Record<string, string>
  input_resolver: string | null
  input: Record<string, unknown>
  /** 单项失败策略: collect/fail_fast */
  on_error: string
}

/** job Agent 清单项(GET /agent/jobs) */
export interface AgentJobInfo {
  agent_key: string
  name: string
  description: string
  agent_kind: string
  decision_mode: string
  version: string
  steps: AgentStepDef[]
  runtime_policy: Record<string, unknown>
}

/** job 运行步骤状态(steps_state 值: 含 when/skip_if 判定结果与展开项明细) */
export interface JobStepState {
  status: string
  reason?: string
  error?: string
  when?: { expr: string; result: boolean }
  counts?: { total?: number; succeeded?: number; failed?: number; skipped?: number }
  items?: Record<string, {
    status: string
    reason?: string
    error?: string | null
    error_class?: string | null
    invocation_id?: string
    degraded?: boolean
    resumed?: boolean
    skip_if?: { expr: string; result: boolean }
  }>
}

/** job 运行详情(GET /agent/job-runs/{id}) */
export interface JobRunDetail {
  job_run_id: string
  agent_key: string
  agent_version: string
  status: string
  progress: { total?: number; processed?: number; percent?: number }
  steps_state: Record<string, JobStepState>
  input_summary: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  task_id: string | null
  entry: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

/** job 运行历史列表项(GET /agent/job-runs, REQ-018 批次 2) */
export interface JobRunListItem {
  job_run_id: string
  agent_key: string
  status: string
  progress: { total?: number; processed?: number; percent?: number }
  error: string | null
  task_id: string | null
  entry: string | null
  created_at: string
  finished_at: string | null
}

/** job 运行历史查询参数(与后端过滤参数对齐) */
export type JobRunListParams = PaginationParams & {
  agent_key?: string
  status_filter?: string
}

/** 断点续跑返回(仅失败/取消态可续) */
export interface JobRunResumeResult {
  job_run_id: string
  status: string
  steps?: Record<string, unknown>
}

/** 自定义 prompt Skill 输入字段声明 */
export interface PromptFieldDef {
  name: string
  /** string/integer/number/boolean */
  type: string
  required: boolean
  description: string
}

/** 自定义 Skill 列表项(GET /agent/skills/custom) */
export interface CustomSkillInfo {
  skill_id: string
  /** 全局键 usr.{key} */
  key: string
  name: string
  description: string
  /** 状态机: draft → published → deprecated */
  status: 'draft' | 'published' | 'deprecated'
  current_version: string
  agent_callable: boolean
  owner_user_id: string
}

/** 自定义 Skill 详情(GET /agent/skills/custom/{id}, 编辑回显数据源: 模板原文/字段声明/输出格式) */
export interface CustomSkillDetail extends CustomSkillInfo {
  template: string
  /** text/json */
  output_format: 'text' | 'json'
  fields: PromptFieldDef[]
}

/** 创建自定义 Skill 请求 */
export interface CustomSkillCreateReq {
  /** 技能短名(注册键 usr.{key}, 小写字母数字下划线) */
  key: string
  name: string
  description?: string
  /** 提示词模板, {{字段}} 占位 */
  template: string
  /** 输出格式: text/json */
  output_format: 'text' | 'json'
  fields: PromptFieldDef[]
  agent_callable: boolean
}

/** 更新自定义 Skill 请求(全字段可选, 已发布更新生成新版本快照) */
export interface CustomSkillUpdateReq {
  name?: string
  description?: string
  template?: string
  output_format?: 'text' | 'json'
  fields?: PromptFieldDef[]
  agent_callable?: boolean
}

// ===== 外部能力: Skill Hub 包 / MCP server(REQ-018 批次 3) =====

/** 包/Server 内技能条目(注册状态回显) */
export interface ExternalSkillEntry {
  /** 技能全局键(pack.{包}.{名} / mcp.{名}.{tool}) */
  key: string
  /** 实现类型: prompt/script/mcp_tool */
  skill_type: string
  /** 是否已注册进运行时注册表 */
  registered: boolean
}

/** Skill Hub 社区包条目(GET /agent/skill-hub/packages) */
export interface SkillHubPackage {
  /** 包命名空间(pack.{包名}) */
  namespace: string
  name: string
  version: string
  status: string
  owner_user_id: string
  skills: ExternalSkillEntry[]
}

/** zip 导入结果(POST /agent/skill-hub/packages) */
export interface SkillHubImportResult {
  namespace: string
  version: string
  /** 注册成功的技能全局键 */
  skills: string[]
  /** 知识资产文件清单(references/, 渐进式披露) */
  references: string[]
  skill_ids: string[]
}

/** MCP server 登记条目(GET /agent/mcp/servers) */
export interface McpServerInfo {
  /** 命名空间(mcp.{name}) */
  namespace: string
  status: string
  owner_user_id: string
  tools: ExternalSkillEntry[]
}

/** MCP server 登记请求(POST /agent/mcp/servers; 连接验证+反射注册) */
export interface McpRegisterReq {
  /** server 名称(不含 '.', 命名空间 mcp.{name}) */
  name: string
  /** stdio 启动命令 */
  command: string
  args?: string[]
  env?: Record<string, string>
}

// ===== 用量统计(REQ-018 批次 3, 计费口径双粒度) =====

/** 按技能聚合的用量行 */
export interface UsageBySkill {
  skill_key: string
  calls: number
  succeeded: number
  degraded: number
  tokens: number
  duration_ms: number
}

/** 按编排 job 聚合的用量行 */
export interface UsageByJob {
  agent_key: string
  runs: number
  succeeded: number
}

/** 用量汇总响应(GET /agent/usage/summary) */
export interface UsageSummary {
  since: string
  by_skill: UsageBySkill[]
  by_agent_job: UsageByJob[]
}
