/**
 * AI 助手展示配置(后台「AI 服务 · AI 助手配置」维护, 悬浮助手消费)
 * - 单例响应式对象: 后台保存后悬浮入口即时生效, 无需刷新页面
 * - 仅保存展示与默认对话参数; 模型绑定仍由「设置 · 模型」按用户维护
 */
import { ref } from 'vue'

/** 悬浮入口位置 */
export type AssistantPosition = 'right' | 'left'

/** AI 助手展示配置 */
export interface AssistantWidgetConfig {
  /** 是否启用悬浮助手按钮 */
  enabled: boolean
  /** 是否在浏览器会话首次加载时自动弹开 */
  autoOpen: boolean
  /** 悬浮按钮位置 */
  position: AssistantPosition
  /** 默认助手 id(空串表示仅知识库) */
  agentId: string
  /** 默认关联知识库 id 列表 */
  projectIds: string[]
  /** 默认深度思考 */
  deepThinking: boolean
  /** 默认联网搜索 */
  enableWebsearch: boolean
  /** 欢迎语(空串使用默认文案) */
  greeting: string
  /** 快捷提问(最多 6 条) */
  suggestions: string[]
}

/** 配置持久化键 */
export const ASSISTANT_CONFIG_STORAGE_KEY = 'ai-assistant-widget-config'
/** 本次会话是否已自动弹开的标记键 */
export const ASSISTANT_AUTO_OPEN_FLAG_KEY = 'ai-assistant-auto-opened'
/** 快捷提问条数上限 */
export const ASSISTANT_MAX_SUGGESTIONS = 6

/** 默认配置 */
export const DEFAULT_ASSISTANT_CONFIG: AssistantWidgetConfig = {
  enabled: true,
  autoOpen: true,
  position: 'right',
  agentId: '',
  projectIds: [],
  deepThinking: false,
  enableWebsearch: false,
  greeting: '',
  suggestions: [
    '帮我总结知识库中的关键信息',
    '根据知识库资料写一份会议纪要',
    '用通俗的语言解释一下向量数据库',
  ],
}

/** 归一化外部数据(容错 localStorage 脏数据/旧版本) */
function normalizeConfig(raw: unknown): AssistantWidgetConfig {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Partial<AssistantWidgetConfig>
  const suggestions = Array.isArray(source.suggestions)
    ? source.suggestions
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter(Boolean)
        .slice(0, ASSISTANT_MAX_SUGGESTIONS)
    : [...DEFAULT_ASSISTANT_CONFIG.suggestions]
  const projectIds = Array.isArray(source.projectIds)
    ? source.projectIds.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
    : []

  return {
    enabled: typeof source.enabled === 'boolean' ? source.enabled : DEFAULT_ASSISTANT_CONFIG.enabled,
    autoOpen: typeof source.autoOpen === 'boolean' ? source.autoOpen : DEFAULT_ASSISTANT_CONFIG.autoOpen,
    position: source.position === 'left' ? 'left' : 'right',
    agentId: typeof source.agentId === 'string' ? source.agentId : '',
    projectIds,
    deepThinking: Boolean(source.deepThinking),
    enableWebsearch: Boolean(source.enableWebsearch),
    greeting: typeof source.greeting === 'string' ? source.greeting : '',
    suggestions,
  }
}

/** 读取本地配置(不可用时回退默认值) */
export function loadAssistantConfig(): AssistantWidgetConfig {
  try {
    const text = localStorage.getItem(ASSISTANT_CONFIG_STORAGE_KEY)
    return text ? normalizeConfig(JSON.parse(text)) : { ...DEFAULT_ASSISTANT_CONFIG }
  } catch {
    return { ...DEFAULT_ASSISTANT_CONFIG }
  }
}

/** 全局响应式配置(后台保存后悬浮入口即时生效) */
export const assistantConfig = ref<AssistantWidgetConfig>(loadAssistantConfig())

/** 保存配置到本地并同步响应式单例 */
export function saveAssistantConfig(next: AssistantWidgetConfig) {
  const normalized = normalizeConfig(next)
  assistantConfig.value = normalized
  try {
    localStorage.setItem(ASSISTANT_CONFIG_STORAGE_KEY, JSON.stringify(normalized))
  } catch {
    /* 隐私模式写入失败时仅内存生效 */
  }
}

/** 恢复默认配置 */
export function resetAssistantConfig() {
  saveAssistantConfig({ ...DEFAULT_ASSISTANT_CONFIG })
}
