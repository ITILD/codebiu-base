// 代码生成器类型(对应后端 /codegen 接口契约)
// 流程: 选表 → 读取表结构 → (可选 AI 建议) → 预览 → 生成

/** 字段控件类型(与后端约定的控件枚举对齐) */
export type CodegenControl =
  | 'input'
  | 'textarea'
  | 'number'
  | 'switch'
  | 'select'
  | 'date'
  | 'datetime'

/** 数据表摘要(列表项) */
export interface CodegenTable {
  /** 表名 */
  name: string
  /** 表注释(可能为空) */
  comment: string | null
  /** 字段数量 */
  column_count: number
}

/** 数据表字段元数据 */
export interface CodegenTableColumn {
  /** 字段名 */
  name: string
  /** 规范化后的类型(后端推断) */
  type: string
  /** 数据库原始类型 */
  sql_type: string
  /** 是否可空 */
  nullable: boolean
  /** 是否主键 */
  primary_key: boolean
  /** 默认值 */
  default: string | null
  /** 字段注释 */
  comment: string | null
  /** 最大长度(无长度限制为 null) */
  max_length: number | null
}

/** 数据表详情 */
export interface CodegenTableDetail {
  name: string
  comment: string | null
  columns: CodegenTableColumn[]
}

/** 智能建议请求 */
export interface CodegenSuggestRequest {
  table_name: string
  /** 是否启用 AI 辅助(关闭则走模板规则) */
  use_ai?: boolean
  module_name?: string
  class_name?: string
}

/** 智能建议返回的字段配置(控件为后端字符串, 前端做枚举归一) */
export interface CodegenSuggestColumn {
  name: string
  label: string
  control: string
  required: boolean
  searchable: boolean
  listable: boolean
  editable: boolean
  dict_type?: string | null
  description?: string | null
  width?: number | null
}

/** 智能建议结果 */
export interface CodegenSuggestResult {
  module_name: string
  class_name: string
  page_title: string
  columns: CodegenSuggestColumn[]
  warnings: string[]
  /** AI 是否实际生效(false 表示回退到模板规则) */
  ai_used: boolean
}

/** 前端可编辑的字段配置(预览/生成共用) */
export interface CodegenFieldConfig {
  name: string
  label: string
  control: CodegenControl
  required: boolean
  searchable: boolean
  listable: boolean
  editable: boolean
  dict_type: string | null
  description: string | null
  width: number
}

/** 预览请求 */
export interface CodegenPreviewRequest {
  table_name: string
  module_name: string
  class_name: string
  page_title: string
  columns: CodegenFieldConfig[]
  /** 是否生成后端七层 */
  include_backend?: boolean
  /** 是否生成前端模块 */
  include_frontend?: boolean
}

/** 生成结果文件 */
export interface CodegenPreviewFile {
  /** 相对项目根路径 */
  path: string
  language: string
  content: string
  /** 目标文件是否已存在 */
  exists: boolean
}

/** 预览结果 */
export interface CodegenPreviewResult {
  files: CodegenPreviewFile[]
  warnings: string[]
}

/** 生成请求(预览参数 + 覆盖开关) */
export type CodegenGenerateRequest = CodegenPreviewRequest & {
  /** 是否覆盖已存在文件 */
  overwrite?: boolean
}

/** 生成结果 */
export interface CodegenGenerateResult {
  written: string[]
  skipped: string[]
  warnings: string[]
}
