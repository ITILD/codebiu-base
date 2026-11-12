<!-- 用量统计面板(REQ-018 批次 3): 按技能/按编排 job 双粒度聚合, days 选择器(7/30/90); 403 优雅降级 -->
<template>
  <div flex flex-col gap-3>
    <div flex flex-wrap items-center gap-2 mb-1>
      <span text-xs text-note-sub>计费口径双粒度汇总(近 {{ days }} 天, 自 {{ sinceText }})</span>
      <div flex-1 />
      <el-radio-group v-model="days" size="small" @change="loadSummary">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 无权限(agent:skill:read): 403 优雅降级为提示而非报错弹窗 -->
    <el-alert
      v-if="forbidden" type="warning" :closable="false"
      title="无用量统计查看权限(agent:skill:read)"
      description="该统计面向管理员/运营口径开放, 普通用户 403 属预期"
    />
    <el-alert v-else-if="loadError" type="error" :closable="false" :title="loadError" />

    <template v-if="!forbidden">
      <div>
        <div mb-2 flex items-center gap-2>
          <span text-sm font-medium>按技能</span>
          <span text-xs text-note-sub>{{ summary?.by_skill.length ?? 0 }} 项</span>
        </div>
        <el-table :data="summary?.by_skill ?? []" v-loading="loading" stripe w-full>
          <el-table-column label="技能键" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.skill_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="calls" label="调用量" width="90" align="center" />
          <el-table-column label="成功率" min-width="140" align="center">
            <template #default="{ row }">
              <el-progress
                :percentage="successRate(row)" :stroke-width="8"
                :status="successRate(row) >= 90 ? 'success' : successRate(row) >= 50 ? undefined : 'exception'"
              />
            </template>
          </el-table-column>
          <el-table-column label="降级" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.degraded > 0" type="warning" size="small">{{ row.degraded }}</el-tag>
              <span v-else text-note-sub>0</span>
            </template>
          </el-table-column>
          <el-table-column label="tokens" width="110" align="center">
            <template #default="{ row }">{{ row.tokens > 0 ? row.tokens.toLocaleString() : '-' }}</template>
          </el-table-column>
          <el-table-column label="累计耗时" width="110" align="center">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
        </el-table>
        <el-empty
          v-if="!loading && !summary?.by_skill.length" :image-size="60"
          description="时间范围内无技能调用"
        />
      </div>

      <div>
        <div mb-2 flex items-center gap-2>
          <span text-sm font-medium>按编排 Job</span>
          <span text-xs text-note-sub>{{ summary?.by_agent_job.length ?? 0 }} 项</span>
        </div>
        <el-table :data="summary?.by_agent_job ?? []" v-loading="loading" stripe w-full>
          <el-table-column label="job 键" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="font-mono text-xs">{{ row.agent_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="runs" label="运行量" width="90" align="center" />
          <el-table-column label="成功率" min-width="140" align="center">
            <template #default="{ row }">
              <el-progress
                :percentage="jobSuccessRate(row)" :stroke-width="8"
                :status="jobSuccessRate(row) >= 90 ? 'success' : jobSuccessRate(row) >= 50 ? undefined : 'exception'"
              />
            </template>
          </el-table-column>
        </el-table>
        <el-empty
          v-if="!loading && !summary?.by_agent_job.length" :image-size="60"
          description="时间范围内无 job 运行"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { getUsageSummary } from '../api/agent'
import type { UsageSummary, UsageBySkill, UsageByJob } from '../types'

const days = ref(30)
const loading = ref(false)
const summary = ref<UsageSummary | null>(null)
const forbidden = ref(false)
const loadError = ref('')

/** 统计起点(since → 本地日期文本) */
const sinceText = computed(() => {
  if (!summary.value?.since) return '-'
  return new Date(summary.value.since).toLocaleDateString('zh-CN')
})

const loadSummary = async () => {
  try {
    loading.value = true
    forbidden.value = false
    loadError.value = ''
    summary.value = await getUsageSummary(days.value)
  } catch (error) {
    // 403 属预期: agent:skill:read 默认不授予普通用户, 优雅降级
    if ((error as { status?: number }).status === 403) {
      forbidden.value = true
    } else {
      loadError.value = error instanceof Error ? error.message : '获取用量统计失败'
    }
    summary.value = null
  } finally {
    loading.value = false
  }
}

/** 技能成功率(百分比, 无调用按 0) */
const successRate = (row: UsageBySkill) =>
  row.calls > 0 ? Math.round((row.succeeded / row.calls) * 100) : 0

/** job 成功率(百分比, 无运行按 0) */
const jobSuccessRate = (row: UsageByJob) =>
  row.runs > 0 ? Math.round((row.succeeded / row.runs) * 100) : 0

/** 累计耗时(ms → 秒/分钟小时) */
const formatDuration = (ms: number) => {
  if (!ms) return '-'
  if (ms < 1000) return `${ms} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`
  return `${(seconds / 3600).toFixed(1)} h`
}

defineExpose({ load: loadSummary })

// 首次挂载即拉取(组件由页签 lazy 渲染, 挂载即用户切入)
onMounted(loadSummary)
</script>
