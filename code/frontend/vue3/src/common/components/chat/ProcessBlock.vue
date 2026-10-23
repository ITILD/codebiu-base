<script setup lang="ts">
// 助手消息"过程区块"折叠展示: 推理过程/意图分析/知识检索引用溯源等
// - 展开后为低调的"日志流"样式: 每条事件为 [图标] 事件：内容 同行排布, 无卡片
// - 知识检索(tool_call)解析引用条目: 来源 + 相关度 + 摘要, 单行省略(悬停看全文)
// - 字号小、色彩暗淡, 弱化过程信息避免喧宾夺主
// - 流式进行中默认展开, 结束后自动折叠为单行入口
import { computed, ref, watch } from 'vue'
import type { MessageBlock } from '@/common/types/chat'
import { StreamEventType, STREAM_TYPE_LABELS } from '@/common/types/chat'
import type { KnowledgeSearchData, KnowledgeSearchResult, WebSearchResult } from '@/common/types/agui'
import {
  MagicStick, Search, DataLine, Link, Document, Warning, ArrowRight,
} from '@element-plus/icons-vue'

interface Props {
  /** 该条助手消息的过程区块列表 */
  blocks: MessageBlock[]
  /** 是否处于流式接收中(影响默认展开) */
  streaming?: boolean
}

const props = defineProps<Props>()

// 区块类型 → 图标组件
const TYPE_ICONS: Record<string, unknown> = {
  [StreamEventType.LLM_THINKING]: MagicStick,
  [StreamEventType.AGENT_THINKING]: MagicStick,
  [StreamEventType.AGENT_THINKING_CONCLUSION]: DataLine,
  [StreamEventType.TOOL_CALL]: Search,
  [StreamEventType.FILE_GEN]: Document,
  [StreamEventType.STATUS]: Link,
  [StreamEventType.ERROR]: Warning,
}

const blockTitle = (block: MessageBlock): string =>
  STREAM_TYPE_LABELS[block.stream_event_type ?? ''] ?? '过程信息'

const blockIcon = (block: MessageBlock): unknown =>
  TYPE_ICONS[block.stream_event_type ?? ''] ?? Link

/** 过程内容按纯文本紧凑展示: 仅去掉首尾空白, 正文不改动 */
const plainContent = (content: string): string => (content ?? '').trim()

/* ===== 知识检索引用解析 ===== */
/** 单条引用: 来源文档 + 相关度 + 内容摘要 */
interface Citation {
  source: string
  score: string
  summary: string
}

/** 引用组: 概述行(检索到 N 条) + 引用列表 + 可选联网引用列表 */
interface CitationGroup {
  overview: string
  citations: Citation[]
  /** 联网搜索引用(与知识片段合并精排后返回, 空则不渲染) */
  web?: WebSearchResult[]
}

/** 从结构化载荷归一化: 兼容旧数组载荷(仅 results)与联网对象载荷(results + web_results) */
const normalizeStructured = (
  data: Record<string, unknown>
): KnowledgeSearchData & { web_results?: WebSearchResult[]; web_count?: number; web_search_error?: string | null } =>
  (Array.isArray(data) ? { results: data as KnowledgeSearchResult[] } : data) as KnowledgeSearchData & {
    web_results?: WebSearchResult[]
    web_count?: number
    web_search_error?: string | null
  }

// 匹配后端检索输出行: "1. [来源] (相关度 0.872) 摘要…"
const CITATION_LINE_RE = /^\d+\.\s*\[(.*?)\]\s*\(相关度\s*([\d.\-*]+)\)\s*(.*)$/

/** 从 tool_call 文本解析引用列表(解析失败返回 null, 走通用文本渲染) */
const parseCitations = (content: string): CitationGroup | null => {
  const lines = content
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  // 首行应为 "检索到 N 条相关片段" 概述
  if (!/^检索到\s*\d+\s*条/.test(lines[0] ?? '')) return null
  const citations: Citation[] = []
  for (const line of lines.slice(1)) {
    const m = line.match(CITATION_LINE_RE)
    if (m) citations.push({ source: m[1], score: m[2], summary: m[3] })
  }
  return citations.length > 0 ? { overview: lines[0], citations } : null
}

/** 结构化检索数据(AG-UI TOOL_CALL_RESULT) → 引用组; 无结果返回 null 走文本回退 */
const fromStructured = (
  data: Record<string, unknown> | null | undefined
): CitationGroup | null => {
  if (!data || typeof data !== 'object') return null
  const d = normalizeStructured(data)
  if (d.search_error) {
    return { overview: `知识库检索失败: ${d.search_error}`, citations: [] }
  }
  const results = Array.isArray(d.results) ? d.results : []
  const webs = Array.isArray(d.web_results) ? d.web_results : []
  if (!results.length && !webs.length) return null
  // 概述行: 知识片段数 + 联网结果数(有则附注); 联网失败附失败原因
  let overview = `检索到 ${d.hit_count ?? results.length} 条相关片段`
  if (d.web_search_error) {
    overview += ` · 网络搜索失败`
  } else if (webs.length) {
    overview += ` · 网络搜索 ${d.web_count ?? webs.length} 条`
  }
  return {
    overview,
    citations: results.map((r) => ({
      source: r.source || '未知来源',
      score:
        typeof r.score === 'number' ? r.score.toFixed(3) : String(r.score ?? '-'),
      summary: r.summary || r.content || '',
    })),
    web: webs,
  }
}

/** 各区块的引用解析结果(type → group): 结构化 data 优先, 文本正则回退(legacy) */
const citationMap = computed(() => {
  const map = new Map<string, CitationGroup>()
  for (const block of props.blocks ?? []) {
    if (block.stream_event_type === StreamEventType.TOOL_CALL) {
      const group = fromStructured(block.data) ?? parseCitations(block.content)
      if (group) map.set(block.id, group)
    }
  }
  return map
})

/** 某区块是否有引用解析结果 */
const hasCitations = (blockId: string): boolean => citationMap.value.has(blockId)

const getCitations = (blockId: string): CitationGroup => citationMap.value.get(blockId) ?? { overview: '', citations: [] }

/* ===== 折叠状态 ===== */
const collapsed = ref(true)

// 流式期间自动展开(看到实时过程), 流式结束后折叠
watch(
  () => props.streaming,
  (streaming) => { collapsed.value = !streaming },
  { immediate: true },
)

const toggle = () => { collapsed.value = !collapsed.value }
</script>

<template>
  <div v-if="blocks?.length" class="mb-2.5 rounded-note-md bg-note-soft overflow-hidden">
    <!-- 折叠头: 摘要入口(点击展开/收起); hover/open 复合态样式保留在 scoped style -->
    <button class="pb-head flex items-center gap-[5px] w-full px-3 py-[5px] border-none bg-transparent text-note-sub text-[11px] cursor-pointer" :class="{ open: !collapsed }" @click="toggle">
      <el-icon :size="12" class="shrink-0 opacity-80"><MagicStick /></el-icon>
      <span class="font-medium">思考与检索过程</span>
      <span class="opacity-[.65]">{{ blocks.length }} 个步骤</span>
      <el-icon :size="11" class="ml-auto transition-transform" :class="!collapsed ? 'rotate-90' : ''">
        <ArrowRight />
      </el-icon>
    </button>

    <!-- 展开内容: 低调日志流, 每条 "事件：内容" 同行 -->
    <div v-show="!collapsed" class="px-3 pt-0.5 pb-2 flex flex-col gap-[3px] opacity-[.92]">
      <div v-for="block in blocks" :key="block.id" class="flex items-start gap-[5px] text-[11px] leading-[1.65] text-[color:var(--el-text-color-secondary,#7c8b80)]">
        <el-icon :size="11" class="shrink-0 mt-[3px] text-note-sub opacity-70">
          <component :is="blockIcon(block)" />
        </el-icon>

        <!-- 知识检索: 标签 + 概述行 + 单行引用条(悬停看全文) + 联网引用(可点击跳转) -->
        <template v-if="hasCitations(block.id)">
          <span class="shrink-0 text-note-deep opacity-[.72]">知识检索：</span>
          <div class="flex-1 min-w-0 flex flex-col gap-px">
            <div class="opacity-70">{{ getCitations(block.id).overview }}</div>
            <div
              v-for="c in getCitations(block.id).citations"
              :key="`${c.source}-${c.score}`"
              class="flex items-baseline gap-1.5 min-w-0 overflow-hidden whitespace-nowrap"
              :title="`${c.source}（相关度 ${c.score}）${c.summary}`"
            >
              <span class="shrink-0 max-w-[38%] text-ellipsis text-note-deep opacity-[.72]">{{ c.source }}</span>
              <span class="shrink-0 text-[10px] font-mono opacity-60">{{ c.score }}</span>
              <span class="flex-1 min-w-0 text-ellipsis opacity-80">{{ c.summary }}</span>
            </div>
            <!-- 联网搜索引用: 标题(外链) + 来源域名 + 相关度 -->
            <div
              v-for="w in getCitations(block.id).web ?? []"
              :key="`web-${w.url}`"
              class="flex items-baseline gap-1.5 min-w-0 overflow-hidden whitespace-nowrap"
              :title="`${w.source}（相关度 ${typeof w.score === 'number' ? w.score.toFixed(3) : '-'}）${w.summary ?? ''}`"
            >
              <a
                :href="w.url"
                target="_blank" rel="noopener noreferrer"
                class="shrink-0 max-w-[52%] text-ellipsis underline decoration-dotted underline-offset-2 text-note-deep opacity-[.78] hover:opacity-100"
              >{{ w.title || w.url }}</a>
              <span class="shrink-0 opacity-60">{{ w.source || 'web' }}</span>
              <span class="shrink-0 text-[10px] font-mono opacity-60">{{ typeof w.score === 'number' ? w.score.toFixed(3) : '-' }}</span>
            </div>
          </div>
        </template>

        <!-- 其他事件: 事件标签与内容同行, 内容原样保留可换行 -->
        <template v-else>
          <span class="shrink-0 text-note-deep opacity-[.72]">{{ blockTitle(block) }}：</span>
          <span class="flex-1 min-w-0 whitespace-pre-wrap break-words opacity-[.88]">{{ plainContent(block.content) }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 折叠头复合态(:hover / .open 同时改底色与文字色, UnoCSS 无法等价表达): 保留在 style */
.pb-head {
  transition: background 0.15s;
}

.pb-head:hover,
.pb-head.open {
  background: var(--note-tint, #e7f3e9);
  color: var(--note-green-deep, #3f7a52);
}
</style>
