<script setup lang="ts">
// 北极星看板(REQ-002 §7): 三项北极星 + 两项下钻
// 数据源: run_finished 事件(run 粒度) + agent_plan_item(项粒度); 只读聚合
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getNorthStarMetrics } from '../api/agent'
import type { NorthStarMetrics } from '../types'

const loading = ref(false)
const forbidden = ref(false)
const days = ref(7)
const metrics = ref<NorthStarMetrics | null>(null)

const pct = (v: number | undefined): string => `${((v ?? 0) * 100).toFixed(1)}%`

const cost = (v: number | undefined): string => {
  if (!v) return '0'
  return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v))
}

const elapsed = (ms: number | undefined): string => {
  if (!ms) return '0s'
  return ms >= 60000 ? `${(ms / 60000).toFixed(1)}min` : `${(ms / 1000).toFixed(0)}s`
}

const load = async () => {
  loading.value = true
  forbidden.value = false
  try {
    metrics.value = await getNorthStarMetrics(days.value)
  } catch (e: unknown) {
    const status = (e as { response?: { status?: number } })?.response?.status
    if (status === 403) {
      forbidden.value = true
    } else {
      ElMessage.error('北极星指标加载失败')
    }
  } finally {
    loading.value = false
  }
}

onMounted(load) 
</script>

<template>
  <div class="north-star">
    <div class="flex items-center gap-2 mb-3">
      <span class="text-sm font-medium">运行看板</span>
      <el-radio-group v-model="days" size="small" @change="load">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
      </el-radio-group>
      <span v-if="metrics" class="text-xs opacity-60">
        {{ metrics.runs }} 次运行 / {{ metrics.items }} 个清单项
      </span>
      <el-button size="small" text class="ml-auto" :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-empty
      v-if="forbidden"
      description="无权限查看运营看板（需 agent:manage:read）"
      :image-size="72"
    />

    <el-skeleton v-else-if="loading && !metrics" :rows="3" animated />

    <div v-else-if="metrics" class="grid grid-cols-1 md:grid-cols-3 gap-3">
      <div class="ns-card">
        <div class="ns-label">任务成功率</div>
        <div class="ns-value">{{ pct(metrics.success_rate) }}</div>
        <div class="ns-hint">stop_reason=completed 的运行占比</div>
      </div>

      <div class="ns-card">
        <div class="ns-label">每成功任务成本</div>
        <div class="ns-value">
          {{ cost(metrics.cost_per_success.tokens) }}
          <span class="text-xs font-normal opacity-60">tokens</span>
        </div>
        <div class="ns-hint">
          {{ metrics.cost_per_success.tool_calls }} 次工具调用 ·
          {{ elapsed(metrics.cost_per_success.elapsed_ms) }}
        </div>
      </div>

      <div class="ns-card">
        <div class="ns-label">假完成率</div>
        <div class="ns-value" :class="{ 'is-bad': metrics.fake_done_rate > 0 }">
          {{ pct(metrics.fake_done_rate) }}
        </div>
        <div class="ns-hint">
          <span v-if="metrics.fake_done_rate > 0" class="text-[color:var(--el-color-danger)]">
            异常：存在标记完成但验收未通过的项（不变量被破坏）
          </span>
          <span v-else>不变量正常：完成必须由验收判定</span>
        </div>
      </div>
    </div>

    <div v-if="!forbidden && metrics" class="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs opacity-75">
      <span>下钻 · 首次交卷通过率：<b>{{ pct(metrics.drilldown.first_submit_pass_rate) }}</b></span>
      <span>下钻 · 预算触顶率：<b>{{ pct(metrics.drilldown.budget_hit_rate) }}</b></span>
    </div>
  </div>
</template>

<style scoped>
.north-star {
  padding: 4px 2px;
}

.ns-card {
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--el-bg-color, #fff);
}

.ns-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  margin-bottom: 6px;
}

.ns-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--el-text-color-primary, #303133);
}

.ns-value.is-bad {
  color: var(--el-color-danger, #f56c6c);
}

.ns-hint {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--el-text-color-secondary, #909399);
}
</style>
