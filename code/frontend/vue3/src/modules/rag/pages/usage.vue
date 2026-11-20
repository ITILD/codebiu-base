<!-- 用量统计页(系统管理员): token/成本汇总卡 + ECharts 趋势分布 + 每轮用量明细(含批量导出) -->
<template>
  <div p-3 md:p-4 w-full>
    <InkPageHead title="用量统计" sub="问答 token 消耗与成本核算" seal="量" />

    <!-- 非管理员提示 -->
    <el-empty v-if="!isAdmin" description="用量统计仅系统管理员可访问" />

    <template v-else>
      <!-- 筛选行: 时间范围切换 -->
      <div mb-3 flex flex-wrap items-center justify-between gap-y-2>
        <el-radio-group v-model="days" @change="handleDaysChange">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="90">近 90 天</el-radio-button>
        </el-radio-group>
        <div flex gap-2>
          <el-button :loading="exporting" :disabled="!tableData.length" @click="handleExportCsv">
            批量导出 CSV
          </el-button>
          <el-button :icon="Refresh" @click="fetchUsage">刷新</el-button>
        </div>
      </div>

      <!-- 用量统计卡 -->
      <div class="usage-stat-cards">
        <div class="usage-stat-card">
          <div class="usage-stat-icon total"><el-icon><Coin /></el-icon></div>
          <div class="usage-stat-meta">
            <div class="usage-stat-label">总 token</div>
            <div class="usage-stat-value">{{ fmtTokens(usage?.summary.total_tokens) }}</div>
          </div>
        </div>
        <div class="usage-stat-card">
          <div class="usage-stat-icon in"><el-icon><Download /></el-icon></div>
          <div class="usage-stat-meta">
            <div class="usage-stat-label">输入 token</div>
            <div class="usage-stat-value">{{ fmtTokens(usage?.summary.total_prompt_tokens) }}</div>
          </div>
        </div>
        <div class="usage-stat-card">
          <div class="usage-stat-icon out"><el-icon><Upload /></el-icon></div>
          <div class="usage-stat-meta">
            <div class="usage-stat-label">输出 token</div>
            <div class="usage-stat-value">{{ fmtTokens(usage?.summary.total_completion_tokens) }}</div>
          </div>
        </div>
        <div class="usage-stat-card">
          <div class="usage-stat-icon cost"><el-icon><Wallet /></el-icon></div>
          <div class="usage-stat-meta">
            <div class="usage-stat-label">成本合计(元)</div>
            <div class="usage-stat-value">{{ fmtCost(usage?.summary.total_cost) }}</div>
          </div>
        </div>
        <div class="usage-stat-card">
          <div class="usage-stat-icon req"><el-icon><ChatDotRound /></el-icon></div>
          <div class="usage-stat-meta">
            <div class="usage-stat-label">调用次数</div>
            <div class="usage-stat-value">{{ fmtTokens(usage?.summary.request_count) }}</div>
            <div class="usage-stat-sub">{{ fmtTokens(usage?.summary.conversation_count) }} 个会话(不含语音/生图)</div>
          </div>
        </div>
        <div class="usage-stat-card">
          <div class="usage-stat-icon user"><el-icon><UserFilled /></el-icon></div>
          <div class="usage-stat-meta">
            <div class="usage-stat-label">活跃用户</div>
            <div class="usage-stat-value">{{ fmtTokens(usage?.summary.active_user_count) }}</div>
          </div>
        </div>
      </div>

      <!-- 用量可视化图表 -->
      <UsageCharts :stats="usage" :loading="usageLoading" />

      <!-- ── 用量明细 ── -->
      <section mt-6>
        <div mb-3 flex flex-wrap items-center gap-y-2>
          <h3 class="section-title">用量明细</h3>
          <el-input
            style="width: min(220px, 100%)"
            class="md:ml-4"
            v-model="modelFilter"
            placeholder="按模型标识过滤"
            clearable
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #append>
              <el-button :icon="Search" @click="handleSearch" />
            </template>
          </el-input>
        </div>

        <el-table :data="tableData" v-loading="loading" border stripe w-full>
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column label="用户" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.nickname || row.username || row.user_id }}
            </template>
          </el-table-column>
          <el-table-column prop="model_name" label="模型" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.model_name || '未记录' }}</template>
          </el-table-column>
          <el-table-column label="模式" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="modeTagType(row.mode)" size="small" effect="plain">
                {{ modeLabel(row.mode) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="输入 token" width="110" align="right">
            <template #default="{ row }">{{ fmtTokens(row.prompt_tokens) }}</template>
          </el-table-column>
          <el-table-column label="输出 token" width="110" align="right">
            <template #default="{ row }">{{ fmtTokens(row.completion_tokens) }}</template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right">
            <template #default="{ row }">
              {{ fmtTokens(row.prompt_tokens + row.completion_tokens) }}
            </template>
          </el-table-column>
          <el-table-column label="成本(元)" width="110" align="right">
            <template #default="{ row }">{{ fmtCost(row.cost) }}</template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTimeShort(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" :fixed="isMd ? 'right' : false">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openConversation(row.conversation_id)">
                查看对话
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div mt-4 flex flex-wrap justify-center sm:justify-end>
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.size"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
            @size-change="fetchRecords"
            @current-change="fetchRecords"
          />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import {
  Search, Refresh, Coin, Download, Upload, Wallet, ChatDotRound, UserFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import { usePermission } from '@/common/composables/usePermission'
import { useResponsive } from '@/common/composables/useResponsive'
import { formatTimeShort } from '@/common/utils/datetime'
import { getUsageStats, getUsageRecords } from '../api/usage'
import type { UsageStats, UsageRecordItem } from '../types/usage'
import UsageCharts from '../components/UsageCharts.vue'

// 用量统计仅系统管理员
const { isAdmin } = usePermission()
const { isMd } = useResponsive()

// ── 用量统计 ──
const days = ref(30)
const usage = ref<UsageStats | null>(null)
const usageLoading = ref(true)

/** token/数量格式化(空数据显示 -) */
const fmtTokens = (value?: number | null) =>
  value == null ? '-' : Number(value).toLocaleString()

/** 成本格式化: 大额两位小数, 小额四位小数(避免精度丢失显示为 0) */
const fmtCost = (value?: number | null) =>
  value == null ? '-' : Number(value) >= 1 ? Number(value).toFixed(2) : Number(value).toFixed(4)

const modeLabel = (mode: string) =>
  ({
    fast: '快速',
    thinking: '思考',
    deep: '深度',
    asr: '语音识别',
    tts: '语音合成',
    image: '生图',
  })[mode] || mode || '-'

const modeTagType = (mode: string): 'primary' | 'warning' | 'danger' | 'success' | 'info' =>
  ({
    fast: 'primary',
    thinking: 'warning',
    deep: 'danger',
    asr: 'success',
    tts: 'success',
    image: 'warning',
  } as const)[mode as 'fast'] || 'info'

const fetchUsage = async () => {
  try {
    usageLoading.value = true
    usage.value = await getUsageStats({ days: days.value })
  } catch (error) {
    console.error('获取用量统计失败:', error)
    ElMessage.error('获取用量统计失败，请重试')
  } finally {
    usageLoading.value = false
  }
}

const handleDaysChange = () => {
  fetchUsage()
  pagination.value.page = 1
  fetchRecords()
}

// ── 用量明细 ──
const modelFilter = ref('')
const pagination = ref<PaginationParams>({ page: 1, size: 10 })
const tableData = ref<UsageRecordItem[]>([])
const total = ref(0)
const loading = ref(false)
const exporting = ref(false)

const fetchRecords = async () => {
  try {
    loading.value = true
    const response: PaginationResponse<UsageRecordItem> = await getUsageRecords({
      ...pagination.value,
      days: days.value,
      model_name: modelFilter.value || undefined,
    })
    tableData.value = response.items
    total.value = response.total
  } catch (error) {
    console.error('获取用量明细失败:', error)
    ElMessage.error('获取用量明细失败，请重试')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.page = 1
  fetchRecords()
}

/** 批量导出当前筛选的全部明细为 CSV(客户端生成, 上限 500/页×翻页拉全量) */
const handleExportCsv = async () => {
  try {
    exporting.value = true
    const all: UsageRecordItem[] = []
    const size = 500
    for (let page = 1; ; page++) {
      const response = await getUsageRecords({
        page, size, days: days.value, model_name: modelFilter.value || undefined,
      })
      all.push(...response.items)
      if (all.length >= response.total || response.items.length === 0) break
    }
    const header = '时间,用户,模型,模式,输入token,输出token,合计token,成本(元)'
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const lines = all.map((r) =>
      [
        formatTimeShort(r.created_at), r.nickname || r.username || r.user_id,
        r.model_name || '未记录', modeLabel(r.mode), r.prompt_tokens,
        r.completion_tokens, r.prompt_tokens + r.completion_tokens, r.cost,
      ].map(esc).join(',')
    )
    const blob = new Blob([`\uFEFF${header}\n${lines.join('\n')}`], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `用量明细_${days.value}天.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${all.length} 条明细`)
  } catch (error) {
    console.error('导出用量明细失败:', error)
    ElMessage.error('导出用量明细失败，请重试')
  } finally {
    exporting.value = false
  }
}

/** 跳转对话记录页并携带会话ID(由目标页处理高亮/抽屉) */
const openConversation = (conversationId: string) => {
  useRouter().push({ path: '/rag/chat-records', query: { conversation_id: conversationId } })
}

onMounted(() => {
  if (isAdmin.value) {
    fetchUsage()
    fetchRecords()
  }
})
</script>

<style scoped>
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-strong);
}

.usage-stat-cards {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.usage-stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--gh-surface);
  border: 1px solid var(--gh-border);
}

.usage-stat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  font-size: 19px;
  flex-shrink: 0;
}

.usage-stat-icon.total { background: color-mix(in srgb, var(--gh-accent) 14%, transparent); color: var(--gh-accent); }
.usage-stat-icon.in { background: color-mix(in srgb, #2e90fa 14%, transparent); color: #2e90fa; }
.usage-stat-icon.out { background: color-mix(in srgb, #12b76a 14%, transparent); color: #12b76a; }
.usage-stat-icon.cost { background: color-mix(in srgb, #f79009 14%, transparent); color: #f79009; }
.usage-stat-icon.req { background: color-mix(in srgb, #7a5af8 14%, transparent); color: #7a5af8; }
.usage-stat-icon.user { background: color-mix(in srgb, #0ba5ec 14%, transparent); color: #0ba5ec; }

.usage-stat-meta { min-width: 0; }

.usage-stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.usage-stat-value {
  margin-top: 3px;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-strong);
  line-height: 1.2;
  white-space: nowrap;
}

.usage-stat-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
}

@media (max-width: 1100px) {
  .usage-stat-cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 560px) {
  .usage-stat-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
