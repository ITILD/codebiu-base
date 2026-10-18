<template>
  <!-- 关系数据库面板: 概览统计 + 图表区 + 数据表清单(数据由本面板拉取, refresh/resize 供页面调度) -->
  <!-- 概览统计 -->
  <div class="stat-row" mb-4>
    <div class="stat-card">
      <div class="stat-icon icon-blue">
        <el-icon :size="22"><Coin /></el-icon>
      </div>
      <div class="stat-meta">
        <div class="stat-value">{{ tableList.length }}</div>
        <div class="stat-label">数据表</div>
      </div>
    </div>
    <div class="stat-card">
      <div class="stat-icon icon-green">
        <el-icon :size="22"><Tickets /></el-icon>
      </div>
      <div class="stat-meta">
        <div class="stat-value">{{ totalRows.toLocaleString() }}</div>
        <div class="stat-label">总记录数</div>
      </div>
    </div>
    <div class="stat-card">
      <div class="stat-icon icon-orange">
        <el-icon :size="22"><Clock /></el-icon>
      </div>
      <div class="stat-meta">
        <div class="stat-value stat-time">{{ lastUpdatedOverall || '-' }}</div>
        <div class="stat-label">最近数据更新</div>
      </div>
    </div>
  </div>

  <!-- 图表区 -->
  <div class="chart-row" mb-4>
    <el-card shadow="never" class="chart-card">
      <template #header>
        <div class="card-head">数据条数 TOP 10</div>
      </template>
      <div ref="barRef" class="chart-box" />
    </el-card>
    <el-card shadow="never" class="chart-card">
      <template #header>
        <div class="card-head">数据量占比</div>
      </template>
      <div ref="pieRef" class="chart-box" />
    </el-card>
  </div>

  <!-- 数据表清单 -->
  <el-card shadow="never">
    <el-table
      :data="tableList"
      v-loading="loading"
      stripe
      w-full
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="#" width="60" />
      <el-table-column prop="name" label="表名" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span font-mono text-13px>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="comment" label="注释" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.comment" text-muted>{{ row.comment }}</span>
          <span v-else text-subtle>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="column_count" label="字段数" width="90" align="center" />
      <el-table-column prop="row_count" label="数据条数" width="120" align="right" sortable>
        <template #default="{ row }">
          <span v-if="row.row_count > 0" font-mono>{{ row.row_count.toLocaleString() }}</span>
          <span v-else font-mono text-subtle>0</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_updated" label="最后更新" width="170" sortable>
        <template #default="{ row }">
          <div v-if="row.last_updated" class="time-cell">
            <span>{{ fmtTime(row.last_updated) }}</span>
            <el-tag v-if="isToday(row.last_updated)" size="small" type="success" effect="plain">
              今天
            </el-tag>
          </div>
          <span v-else text-subtle>-</span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty
      v-if="!loading && tableList.length === 0"
      :description="keyword ? '没有匹配的数据表' : '暂无数据表'"
      :image-size="72"
    />
  </el-card>
</template>

<script setup lang="ts">
// 关系数据库面板: 自行拉取数据表清单并渲染统计/图表;
// expose.refresh 供页面刷新调度, expose.resize 供切回本 tab 时图表自适应宽度
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Coin, Tickets, Clock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
// echarts 按需引入
import * as echarts from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { listDbTables, type DbTableInfo } from '@/modules/main/api/db'

echarts.use([
  BarChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])

const props = defineProps<{
  /** 表名/注释搜索关键字(页面头部搜索框传入, 回车/清空时由页面触发 refresh) */
  keyword?: string
}>()

const loading = ref(false)
const tableList = ref<DbTableInfo[]>([])

// ==================== 图表 ====================
const barRef = ref<HTMLElement>()
const pieRef = ref<HTMLElement>()
let barChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

/** 图表主题色 */
const CHART_COLORS = [
  '#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#8d6ceb',
  '#36a3f7', '#00bfa5', '#ffb35c', '#f0609e', '#7f8fa6',
]

/** 按 row_count 取前 N 的表 */
const topTables = computed(() =>
  [...tableList.value].sort((a, b) => b.row_count - a.row_count),
)

/** 渲染柱状图(TOP10 数据条数) */
const renderBar = () => {
  if (!barRef.value) return
  const top = topTables.value.slice(0, 10).reverse()
  barChart ??= echarts.init(barRef.value)
  barChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (v: unknown) => Number(v).toLocaleString(),
    },
    grid: { left: 8, right: 32, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: (v: number) => (v >= 1000 ? `${v / 1000}k` : String(v)), color: 'var(--el-text-color-secondary)' },
      splitLine: { lineStyle: { type: 'dashed', color: 'var(--el-border-color-lighter)' } },
    },
    yAxis: {
      type: 'category',
      data: top.map(t => t.name),
      axisLabel: { fontSize: 11, color: 'var(--el-text-color-secondary)' },
    },
    series: [{
      type: 'bar',
      data: top.map((t, i) => ({
        value: t.row_count,
        itemStyle: {
          borderRadius: [0, 4, 4, 0],
          color: CHART_COLORS[(top.length - 1 - i) % CHART_COLORS.length],
        },
      })),
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        formatter: ({ value }: { value: number }) => value.toLocaleString(),
        fontSize: 11,
        color: 'var(--el-text-color-secondary)',
      },
    }],
  })
}

/** 渲染环形图(数据量占比) */
const renderPie = () => {
  if (!pieRef.value) return
  const top = topTables.value.filter(t => t.row_count > 0)
  const head = top.slice(0, 8)
  const restRows = top.slice(8).reduce((s, t) => s + t.row_count, 0)
  const data = head.map((t, i) => ({
    name: t.name,
    value: t.row_count,
    itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] },
  }))
  if (restRows > 0) {
    data.push({ name: '其他', value: restRows, itemStyle: { color: 'var(--el-border-color)' } })
  }
  pieChart ??= echarts.init(pieRef.value)
  pieChart.setOption({
    tooltip: {
      trigger: 'item',
      valueFormatter: (v: unknown) => Number(v).toLocaleString(),
    },
    legend: {
      orient: 'vertical',
      right: 8,
      top: 'middle',
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: 'var(--el-text-color-secondary)' },
    },
    series: [{
      type: 'pie',
      center: ['35%', '50%'],
      radius: ['45%', '72%'],
      data,
      label: { show: false },
      itemStyle: { borderRadius: 4, borderColor: 'var(--el-bg-color)', borderWidth: 2 },
      emphasis: {
        label: { show: false },
        scaleSize: 6,
      },
    }],
  })
}

/** 数据变化后重绘图表 */
watch(tableList, () => nextTick(() => {
  renderBar()
  renderPie()
}))

/** 窗口尺寸变化时自适应 */
const handleResize = () => {
  barChart?.resize()
  pieChart?.resize()
}

// ==================== 统计 ====================
/** 总记录数 */
const totalRows = computed(() =>
  tableList.value.reduce((sum, t) => sum + (t.row_count || 0), 0),
)

/** 全库最近一次数据更新时间 */
const lastUpdatedOverall = computed(() => {
  const times = tableList.value
    .map(t => t.last_updated)
    .filter((t): t is string => !!t)
    .sort()
  return times.length ? fmtTime(times[times.length - 1]) : ''
})

/** 格式化时间:YYYY-MM-DD HH:mm */
const fmtTime = (iso: string) => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 是否为今天更新 */
const isToday = (iso: string) => {
  const d = new Date(iso)
  const now = new Date()
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate()
}

/** 最近 24h 内有更新的表行高亮 */
const rowClassName = ({ row }: { row: DbTableInfo }) =>
  row.last_updated && isToday(row.last_updated) ? 'row-active' : ''

// ==================== 数据拉取 ====================
/** 刷新数据表清单(供页面调度), 返回是否成功 */
const refresh = async (): Promise<boolean> => {
  try {
    loading.value = true
    tableList.value = await listDbTables(props.keyword)
    return true
  } catch (error) {
    console.error('获取数据表清单失败:', error)
    ElMessage.error('获取数据表清单失败')
    return false
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  // 生命周期清理: 移除监听并销毁图表实例
  window.removeEventListener('resize', handleResize)
  barChart?.dispose()
  pieChart?.dispose()
  barChart = null
  pieChart = null
})

defineExpose({
  /** 拉取数据表清单 */
  refresh,
  /** 重绘图表适配容器宽度 */
  resize: handleResize,
})
</script>

<style scoped>
/* 概览统计卡片 */
.stat-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 180px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  transition: box-shadow 0.2s;
}

.stat-card:hover {
  box-shadow: var(--el-box-shadow-light);
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 8px;
  flex-shrink: 0;
}

.icon-blue {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.icon-green {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.icon-orange {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 卡片头部标题 */
.card-head {
  font-size: 14px;
  font-weight: 600;
}

/* 图表区 */
.chart-row {
  display: flex;
  gap: 16px;
}

.chart-card {
  flex: 1;
  min-width: 0;
}

.chart-box {
  width: 100%;
  height: 300px;
}

/* 文本色工具类 */
.text-muted {
  color: var(--el-text-color-secondary);
}

.text-subtle {
  color: var(--el-text-color-placeholder);
}

/* 最后更新单元格:时间 + 今天标签 */
.time-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}

/* 今日有更新的表行背景 */
:deep(.el-table .row-active) {
  background: var(--el-color-success-light-9);
}
</style>
