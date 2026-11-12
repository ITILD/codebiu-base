// src/modules/agent/types/labels.ts
// 能力平台枚举标签映射(REQ-018): 调用状态 / Skill 性质 / 业务分类 / 发布状态
/** 标签颜色类型(与 Element Plus el-tag type 对齐) */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** 调用/运行通用状态中文标签 */
export const statusLabel = (status: string): string => ({
  pending: '等待中',
  running: '运行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  skipped: '已跳过',
}[status] ?? status)

/** 调用/运行通用状态标签颜色 */
export const statusTagType = (status: string): TagType =>
  (({ pending: 'info', running: 'primary', succeeded: 'success', failed: 'danger', cancelled: 'warning', skipped: 'info' }) as Record<string, TagType>)[status] ?? 'info'

/** Skill 能力来源标签 */
export const natureLabel = (nature: string): string => ({
  static: '静态',
  ai: '模型',
  hybrid: '混合',
}[nature] ?? nature)

/** Skill 能力来源标签颜色(static=零模型可跑/ai=必需模型/hybrid=可降级) */
export const natureTagType = (nature: string): TagType =>
  (({ static: 'success', ai: 'danger', hybrid: 'warning' }) as Record<string, TagType>)[nature] ?? 'info'

/** Skill 业务分类标签 */
export const categoryLabel = (category: string): string => ({
  ingest: '入库',
  retrieval: '检索',
  generation: '生成',
  governance: '治理',
  action: '动作',
}[category] ?? category)

/** 自定义 Skill 发布状态标签 */
export const publishStatusLabel = (status: string): string => ({
  draft: '草稿',
  published: '已发布',
  deprecated: '已下线',
}[status] ?? status)

/** 自定义 Skill 发布状态标签颜色(状态机 draft→published→deprecated) */
export const publishStatusTagType = (status: string): TagType =>
  (({ draft: 'info', published: 'success', deprecated: 'danger' }) as Record<string, TagType>)[status] ?? 'info'

/** Skill 实现类型标签(REQ-018 批次 3: 含外部能力 mcp_tool/script/python_script) */
export const skillTypeLabel = (skillType: string): string => ({
  prompt: '提示词',
  builtin_tool: '内置工具',
  mcp_tool: 'MCP 工具',
  python_script: 'Python 脚本',
  script: '脚本',
}[skillType] ?? skillType)

/** Skill 实现类型标签颜色(外部能力 mcp_tool/script/python_script 高亮区分内置) */
export const skillTypeTagType = (skillType: string): TagType =>
  (({ prompt: 'info', builtin_tool: 'info', mcp_tool: 'warning', python_script: 'warning', script: 'warning' }) as Record<string, TagType>)[skillType] ?? 'info'
