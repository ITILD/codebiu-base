<script setup lang="ts">
/**
 * 成本与用量治理 · 可视化图表(ECharts)
 * 三块图:
 *   1. 每日用量趋势: 输入/输出 token 堆叠柱状(tooltip 附成本与轮次)
 *   2. 用户用量排行: TOP N 输入/输出 token 横向堆叠条形
 *   3. 模型用量分布: 各模型总 token 环形占比(图例带成本)
 * 数据全部来自 /rag/usage/stats, 前端只做展示。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { UsageStats } from '../types/usage'

echarts.use([
  BarChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

const props = defineProps<{
  stats: UsageStats | null
  loading?: boolean
}>()

/* 画布内不解析 CSS 变量, 渲染前从根节点解析为实际色值, 兼容深色主题 */
const resolveColor = (name: string, fallback: string) => {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

const chartColors = () => ({
  text: resolveColor('--text-strong', '#101828'),
  muted: resolveColor('--text-muted', '#667085'),
  axis: resolveColor('--text-muted', '#98a2b3'),
  split: resolveColor('--border-subtle', '#eaecf0'),
  surface: resolveColor('--bg-surface', '#ffffff'),
})

/** 输入/输出双系列统一配色 */
const SERIES_COLORS = { prompt: '#2e90fa', completion: '#12b76a' }

const formatTokens = (v: unknown) => Number(v ?? 0).toLocaleString()
const formatCost = (v: unknown) => `¥${Number(v ?? 0).toFixed(4)}`

const trendRef = ref<HTMLElement>()
const userRef = ref<HTMLElement>()
const modelRef = ref<HTMLElement>()

let trendChart: echarts.ECharts | null = null
let userChart: echarts.ECharts | null = null
let modelChart: echarts.ECharts | null = null

const totalTokens = () => props.stats?.summary.total_tokens ?? 0

/** 每日用量趋势(输入/输出堆叠柱状 + 成本折线副轴) */
const renderTrend = () => {
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  const colors = chartColors()
  const daily = props.stats?.daily ?? []
  trendChart.setOption(
    {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params]
          const day = list[0] && typeof list[0] === 'object' && 'name' in (list[0] as object)
            ? String((list[0] as { name?: string }).name ?? '')
            : ''
          const item = daily.find((d) => d.date === day)
          const lines = list
            .filter((p) => (p as { seriesType?: string }).seriesType !== 'line' || (p as { value?: number }).value != null)
            .map((p) => {
              const { seriesName, value, color } = p as { seriesName?: string; value?: number; color?: string }
              return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>${seriesName ?? ''}：${formatTokens(value)}`
            })
          lines.push(
            `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f79009;margin-right:6px"></span>成本：${formatCost(item?.cost ?? 0)}（${item?.requests ?? 0} 轮）`,
          )
          return `<b>${day}</b><br/>${lines.join('<br/>')}`
        },
      },
      legend: {
        top: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        itemGap: 16,
        textStyle: { fontSize: 12, color: colors.muted },
      },
      grid: { left: 8, right: 8, top: 32, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        data: daily.map((d) => d.date.slice(5)),
        axisLabel: { color: colors.axis, fontSize: 11 },
        axisLine: { lineStyle: { color: colors.split } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          color: colors.axis,
          fontSize: 11,
          formatter: (v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${v}`),
        },
        splitLine: { lineStyle: { type: 'dashed', color: colors.split } },
      },
      series: [
        {
          name: '输入 token',
          type: 'bar',
          stack: 'tokens',
          barMaxWidth: 22,
          itemStyle: { color: SERIES_COLORS.prompt, borderRadius: [0, 0, 0, 0] },
          data: daily.map((d) => d.prompt_tokens),
        },
        {
          name: '输出 token',
          type: 'bar',
          stack: 'tokens',
          barMaxWidth: 22,
          itemStyle: { color: SERIES_COLORS.completion, borderRadius: [3, 3, 0, 0] },
          data: daily.map((d) => d.completion_tokens),
        },
      ],
    },
    true,
  )
}

/** 用户用量排行(横向堆叠条形, 展示名优先用户名) */
const renderUsers = () => {
  if (!userRef.value) return
  if (!userChart) userChart = echarts.init(userRef.value)
  const colors = chartColors()
  const users = [...(props.stats?.top_users ?? [])].reverse()
  const nameOf = (u: { username?: string | null; nickname?: string | null }) =>
    u.nickname || u.username || '未知用户'
  userChart.setOption(
    {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params]
          const first = list[0] as { name?: string } | undefined
          const user = [...users].reverse().find((u) => nameOf(u) === first?.name)
          const lines = list.map((p) => {
            const { seriesName, value, color } = p as { seriesName?: string; value?: number; color?: string }
            return `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>${seriesName ?? ''}：${formatTokens(value)}`
          })
          lines.push(`成本：${formatCost(user?.cost ?? 0)}（${user?.requests ?? 0} 轮）`)
          return `<b>${first?.name ?? ''}</b><br/>${lines.join('<br/>')}`
        },
      },
      legend: {
        top: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { fontSize: 12, color: colors.muted },
      },
      grid: { left: 8, right: 56, top: 28, bottom: 4, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: {
          color: colors.axis,
          fontSize: 11,
          formatter: (v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${v}`),
        },
        splitLine: { lineStyle: { type: 'dashed', color: colors.split } },
      },
      yAxis: {
        type: 'category',
        data: users.map(nameOf),
        axisLabel: { color: colors.muted, fontSize: 12 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: '输入 token',
          type: 'bar',
          stack: 'tokens',
          barMaxWidth: 16,
          itemStyle: { color: SERIES_COLORS.prompt },
          data: users.map((u) => u.prompt_tokens),
        },
        {
          name: '输出 token',
          type: 'bar',
          stack: 'tokens',
          barMaxWidth: 16,
          itemStyle: { color: SERIES_COLORS.completion, borderRadius: [0, 3, 3, 0] },
          data: users.map((u) => u.completion_tokens),
          label: {
            show: true,
            position: 'right',
            color: colors.text,
            fontSize: 11,
            fontWeight: 600,
            formatter: ({ dataIndex }: { dataIndex: number }) => {
              const u = [...users].reverse()[dataIndex]
              return formatTokens((u?.prompt_tokens ?? 0) + (u?.completion_tokens ?? 0))
            },
          },
        },
      ],
    },
    true,
  )
}

/** 模型用量分布(环形, 图例带成本) */
const renderModels = () => {
  if (!modelRef.value) return
  if (!modelChart) modelChart = echarts.init(modelRef.value)
  const colors = chartColors()
  const models = props.stats?.by_model ?? []
  const data = models.map((m) => ({
    name: m.model_name,
    value: m.prompt_tokens + m.completion_tokens,
    cost: m.cost,
  }))
  const total = data.reduce((sum, d) => sum + d.value, 0)
  const palette = ['#2e90fa', '#12b76a', '#7a5af8', '#f79009', '#0ba5ec', '#f04438', '#667085']
  modelChart.setOption(
    {
      tooltip: {
        trigger: 'item',
        formatter: (params: unknown) => {
          const p = (Array.isArray(params) ? params[0] : params) as {
            name?: string
            value?: number
          }
          const value = Number(p?.value ?? 0)
          const percent = total > 0 ? `${Math.round((value / total) * 100)}%` : '0%'
          return `${p?.name ?? ''}：${formatTokens(value)} token（${percent}）`
        },
      },
      title: {
        text: formatTokens(total),
        subtext: '总 token',
        left: '32%',
        top: '40%',
        textAlign: 'center',
        textStyle: { fontSize: 22, fontWeight: 600, color: colors.text },
        subtextStyle: { fontSize: 12, color: colors.muted },
      },
      legend: {
        orient: 'vertical',
        right: 8,
        top: 'middle',
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        itemGap: 10,
        textStyle: { fontSize: 11.5, color: colors.muted },
        formatter: (name: string) => {
          const item = data.find((d) => d.name === name)
          const value = item?.value ?? 0
          const percent = total > 0 ? `${Math.round((value / total) * 100)}%` : '0%'
          return `${name}  ${formatTokens(value)}（${percent} · ${formatCost(item?.cost ?? 0)}）`
        },
      },
      series: [
        {
          type: 'pie',
          center: ['32%', '52%'],
          radius: ['54%', '72%'],
          avoidLabelOverlap: true,
          label: { show: false },
          labelLine: { show: false },
          itemStyle: { borderColor: colors.surface, borderWidth: 2 },
          data: data.map((d, i) => ({
            name: d.name,
            value: d.value,
            itemStyle: { color: palette[i % palette.length], borderRadius: 4 },
          })),
        },
      ],
    },
    true,
  )
}

const renderAll = () => {
  renderTrend()
  renderUsers()
  renderModels()
}

const handleResize = () => {
  trendChart?.resize()
  userChart?.resize()
  modelChart?.resize()
}

watch(
  () => props.stats,
  () => nextTick(renderAll),
  { deep: true },
)

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  await nextTick()
  renderAll()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  userChart?.dispose()
  modelChart?.dispose()
  trendChart = null
  userChart = null
  modelChart = null
})
</script>

<template>
  <section class="usage-charts">
    <div class="usage-chart-card is-full">
      <div class="usage-chart-head">
        <div>
          <span class="usage-chart-title">每日用量趋势</span>
          <span class="usage-chart-sub">输入 / 输出 token · 悬停查看成本与轮次</span>
        </div>
      </div>
      <div class="usage-chart-body">
        <div ref="trendRef" class="usage-chart is-trend" />
        <div v-if="!loading && totalTokens() === 0" class="usage-chart-empty">
          暂无用量数据，用户完成问答后此处自动统计
        </div>
      </div>
    </div>

    <div class="usage-chart-card">
      <div class="usage-chart-head">
        <div>
          <span class="usage-chart-title">用户用量排行</span>
          <span class="usage-chart-sub">按总 token 取 TOP</span>
        </div>
      </div>
      <div class="usage-chart-body">
        <div ref="userRef" class="usage-chart" />
        <div v-if="!loading && (stats?.top_users.length ?? 0) === 0" class="usage-chart-empty">
          暂无用户用量
        </div>
      </div>
    </div>

    <div class="usage-chart-card">
      <div class="usage-chart-head">
        <div>
          <span class="usage-chart-title">模型用量分布</span>
          <span class="usage-chart-sub">图例附成本快照</span>
        </div>
      </div>
      <div class="usage-chart-body">
        <div ref="modelRef" class="usage-chart" />
        <div v-if="!loading && (stats?.by_model.length ?? 0) === 0" class="usage-chart-empty">
          暂无模型用量
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.usage-charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.usage-chart-card.is-full {
  grid-column: 1 / -1;
}

.usage-chart-card {
  display: flex;
  flex-direction: column;
  padding: 16px 18px 12px;
  border: 1px solid var(--gh-border);
  border-radius: 14px;
  background: var(--gh-surface, #fff);
}

.usage-chart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.usage-chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-strong);
}

.usage-chart-sub {
  margin-left: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.usage-chart-body {
  position: relative;
  flex: 1;
  min-height: 0;
}

.usage-chart {
  width: 100%;
  height: 240px;
}

.usage-chart.is-trend {
  height: 260px;
}

.usage-chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--text-muted);
  pointer-events: none;
}

@media (max-width: 768px) {
  .usage-charts {
    grid-template-columns: 1fr;
  }
}
</style>
