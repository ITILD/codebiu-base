<script setup lang="ts">
// 助手回答下方的"参考来源"引用栏: 将过程区块中折叠的检索引用, 提升为答案尾部可点击的分组 chips
// - 引用按来源文档分组: 序号角标 + 文档名 + 命中次数("N 处"), 点击打开详情抽屉查看完整摘要
// - 联网搜索结果作为独立分组(标题 + 链接 + 摘要)
// - 超过 6 个分组时折叠, "+M" 展开; 答案流式生成期间不渲染(过程区已实时展示检索)
import { computed, ref } from 'vue'
import { Collection, Link } from '@element-plus/icons-vue'
import type { MessageBlock } from '@/common/types/chat'
import { StreamEventType } from '@/common/types/chat'
import type { KnowledgeSearchData, KnowledgeSearchResult, WebSearchResult } from '@/common/types/agui'

interface Props {
  /** 该条助手消息的过程区块列表 */
  blocks: MessageBlock[]
  /** 是否处于流式接收中(流式中不渲染, 结束后随答案一起出现) */
  streaming?: boolean
}

const props = defineProps<Props>()

/** 单条引用条目 */
interface CitationEntry {
  source: string
  score: string
  summary: string
}

/** 来源分组: 知识库文档或联网搜索 */
interface SourceGroup {
  key: string
  /** 展示名(来源路径最后一段) */
  name: string
  /** 完整来源(悬浮提示) */
  full: string
  entries: CitationEntry[]
  web?: WebSearchResult[]
}

const COLLAPSE_LIMIT = 6

/** 结构化载荷归一化(兼容旧数组载荷与联网对象载荷) */
const normalizeStructured = (
  data: Record<string, unknown>,
): KnowledgeSearchData & { web_results?: WebSearchResult[] } =>
  (Array.isArray(data) ? { results: data as KnowledgeSearchResult[] } : data) as KnowledgeSearchData & {
    web_results?: WebSearchResult[]
  }

// 匹配后端检索输出行: "1. [来源] (相关度 0.872) 摘要…"(legacy 文本回退)
const CITATION_LINE_RE = /^\d+\.\s*\[(.*?)\]\s*\(相关度\s*([\d.\-*]+)\)\s*(.*)$/

/** 从全部 TOOL_CALL 区块聚合引用(结构化 data 优先, 文本正则回退), 按来源分组 */
const groups = computed<SourceGroup[]>(() => {
  const bySource = new Map<string, SourceGroup>()
  const webs: WebSearchResult[] = []
  for (const block of props.blocks ?? []) {
    if (block.stream_event_type !== StreamEventType.TOOL_CALL) continue
    let entries: CitationEntry[] = []
    // 1) 结构化载荷
    if (block.data && typeof block.data === 'object') {
      const d = normalizeStructured(block.data as Record<string, unknown>)
      const results = Array.isArray(d.results) ? d.results : []
      entries = results.map(r => ({
        source: r.source || '未知来源',
        score: typeof r.score === 'number' ? r.score.toFixed(3) : String(r.score ?? '-'),
        summary: r.summary || r.content || '',
      }))
      if (Array.isArray(d.web_results)) webs.push(...d.web_results)
    }
    // 2) 文本正则回退(legacy)
    if (!entries.length && block.content) {
      for (const line of block.content.split('\n')) {
        const m = line.trim().match(CITATION_LINE_RE)
        if (m) {
          entries.push({ source: m[1], score: m[2], summary: m[3] })
        }
      }
    }
    for (const e of entries) {
      let g = bySource.get(e.source)
      if (!g) {
        g = {
          key: e.source,
          name: e.source.split(/[\\/]/).pop() || e.source,
          full: e.source,
          entries: [],
        }
        bySource.set(e.source, g)
      }
      g.entries.push(e)
    }
  }
  const result = [...bySource.values()]
  if (webs.length) {
    result.push({
      key: '__web__',
      name: `联网搜索 · ${webs.length} 条`,
      full: '网络搜索结果',
      entries: [],
      web: webs,
    })
  }
  return result
})

/** 是否有可展示的引用 */
const hasSources = computed(() => !props.streaming && groups.value.length > 0)

/** 折叠态(超过 COLLAPSE_LIMIT 个分组时) */
const expanded = ref(false)
const visibleGroups = computed(() =>
  expanded.value || groups.value.length <= COLLAPSE_LIMIT
    ? groups.value
    : groups.value.slice(0, COLLAPSE_LIMIT),
)
const hiddenCount = computed(() => groups.value.length - visibleGroups.value.length)

/* ===== 详情抽屉 ===== */
const drawerGroup = ref<SourceGroup | null>(null)
const drawerVisible = ref(false)

const openGroup = (g: SourceGroup) => {
  drawerGroup.value = g
  drawerVisible.value = true
}
</script>

<template>
  <div v-if="hasSources" class="mt-2 flex flex-wrap items-center gap-1.5">
    <span class="inline-flex items-center gap-1 text-note-sub text-xs select-none">
      <el-icon :size="12"><Collection /></el-icon>参考来源
    </span>
    <button
      v-for="(g, i) in visibleGroups" :key="g.key"
      class="group/chip inline-flex items-center gap-1.5 max-w-[240px] px-2 py-[3px] rounded-note-md border border-[color:var(--note-border,#e2e8e3)] bg-note-tint text-note-deep text-[0.72rem] cursor-pointer note-transition hover:bg-note-green/15 hover:border-note-green"
      :title="g.full"
      @click="openGroup(g)"
    >
      <span class="shrink-0 w-4 h-4 rounded-[4px] bg-note-green/85 text-white text-[0.62rem] flex-center">{{ i + 1 }}</span>
      <span class="truncate">{{ g.name }}</span>
      <span v-if="g.entries.length > 1" class="shrink-0 text-note-sub">{{ g.entries.length }} 处</span>
      <el-icon v-if="g.web" :size="11" class="shrink-0"><Link /></el-icon>
    </button>
    <button
      v-if="hiddenCount > 0"
      class="px-1.5 py-[3px] border-none rounded-note-md bg-transparent text-note-sub text-[0.72rem] cursor-pointer note-transition hover:text-note-green"
      @click="expanded = true"
    >
      +{{ hiddenCount }} 更多
    </button>

    <!-- 引用详情抽屉: 该来源下全部命中片段(相关度 + 完整摘要) -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerGroup?.full ?? '引用详情'"
      size="min(480px, 92vw)"
      append-to-body
    >
      <div class="flex flex-col gap-3">
        <div
          v-for="(e, i) in drawerGroup?.entries ?? []" :key="i"
          class="rounded-note-md bg-note-tint px-3 py-2"
        >
          <div class="flex items-center gap-2 text-xs text-note-sub">
            <span class="font-medium text-note-green">#{{ i + 1 }}</span>
            <span>相关度 {{ e.score }}</span>
          </div>
          <p class="mt-1.5 text-[0.82rem] leading-[1.7] text-note-deep whitespace-pre-wrap break-words">
            {{ e.summary }}
          </p>
        </div>
        <div
          v-for="(w, i) in drawerGroup?.web ?? []" :key="`w${i}`"
          class="rounded-note-md bg-note-tint px-3 py-2"
        >
          <a
            :href="w.url" target="_blank" rel="noopener noreferrer"
            class="inline-flex items-center gap-1 text-[0.82rem] text-note-green font-medium hover:underline"
          >
            <el-icon :size="12"><Link /></el-icon>{{ w.title || w.url }}
          </a>
          <p v-if="w.summary" class="mt-1 text-xs leading-[1.7] text-note-sub whitespace-pre-wrap break-words">
            {{ w.summary }}
          </p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>
