<!-- job 运行详情对话框: 进度/步骤状态(when/skip_if 判定/展开项明细), 失败支持断点续跑(REQ-018) -->
<template>
  <el-dialog v-model="dialogVisible" title="Job 运行详情" width="92%" class="max-w-[760px]">
    <div v-loading="loading" min-h-40>
      <template v-if="run">
        <div mb-3 flex flex-wrap items-center gap-2>
          <el-tag :type="statusTagType(run.status)" size="small">{{ statusLabel(run.status) }}</el-tag>
          <span text-sm font-medium>{{ run.agent_key }}</span>
          <span text-xs text-note-sub>版本 {{ run.agent_version }} · 入口 {{ run.entry ?? '-' }}</span>
          <div flex-1 />
          <el-button
            v-if="canResume" type="warning" size="small" :loading="resuming" @click="handleResume"
          >
            断点续跑
          </el-button>
        </div>

        <!-- 总进度 -->
        <el-progress
          :percentage="Math.round(run.progress?.percent ?? 0)" :stroke-width="10"
          :status="run.status === 'failed' ? 'exception' : run.status === 'succeeded' ? 'success' : undefined"
        />
        <div mt-1 text-xs text-note-sub>
          已处理 {{ run.progress?.processed ?? 0 }} / {{ run.progress?.total ?? 0 }} 项
          · 开始 {{ formatTime(run.started_at) }} · 结束 {{ formatTime(run.finished_at) }}
          <template v-if="run.task_id"> · 队列任务 {{ run.task_id }}</template>
        </div>

        <el-alert
          v-if="run.error" type="error" :closable="false" mt-2
          :title="run.error"
        />

        <!-- 步骤状态表(steps_state: 含 when/skip_if 判定结果与展开项明细) -->
        <el-table :data="stepRows" border size="small" mt-3>
          <el-table-column prop="id" label="步骤" min-width="110" show-overflow-tooltip />
          <el-table-column label="状态" width="86" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="计数 (成/败/跳/总)" min-width="130" align="center">
            <template #default="{ row }">
              {{ row.counts?.succeeded ?? 0 }} / {{ row.counts?.failed ?? 0 }} /
              {{ row.counts?.skipped ?? 0 }} / {{ row.counts?.total ?? 0 }}
            </template>
          </el-table-column>
          <el-table-column label="when 判定" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="row.when">
                {{ row.when.result ? '放行' : '拦截' }}: {{ row.when.expr }}
              </template>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column label="异常/原因" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.error" class="text-[var(--el-color-danger)]">{{ row.error }}</span>
              <span v-else-if="row.reason" text-note-sub>{{ row.reason }}</span>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column label="明细" width="80" align="center">
            <template #default="{ row }">
              <el-button v-if="row.items && Object.keys(row.items).length" link type="primary" size="small"
                @click="activeItemStep = activeItemStep === row.id ? '' : row.id"
              >
                {{ activeItemStep === row.id ? '收起' : '展开' }}
              </el-button>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 展开项明细(items: 每项状态/skip_if 判定/降级/错误/续跑复用标记) -->
        <el-table
          v-if="activeItemStep && itemRows.length" :data="itemRows" border size="small" mt-2
        >
          <el-table-column label="展开项" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.key }}
              <el-tag v-if="row.item.resumed" type="warning" size="small" ml-1>续跑复用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.item.status)" size="small">
                {{ statusLabel(row.item.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="降级" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.item.degraded" type="warning" size="small">降级</el-tag>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column label="skip_if 判定" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="row.item.skip_if">
                {{ row.item.skip_if.result ? '跳过' : '执行' }}: {{ row.item.skip_if.expr }}
              </template>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
          <el-table-column label="错误/原因" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.item.error" class="text-[var(--el-color-danger)]">
                {{ row.item.error_class ? `${row.item.error_class}: ` : '' }}{{ row.item.error }}
              </span>
              <span v-else-if="row.item.reason" text-note-sub>{{ row.item.reason }}</span>
              <span v-else text-note-sub>-</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 聚合结果摘要 -->
        <div v-if="run.result" mt-3>
          <div text-xs text-note-sub mb-1>聚合结果</div>
          <pre class="m-0 p-2 text-xs rounded bg-[var(--el-fill-color-light)] overflow-auto max-h-50
            whitespace-pre-wrap break-all">{{ formatJson(run.result) }}</pre>
        </div>
      </template>
    </div>
    <template #footer>
      <span>
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="loading" @click="load(run?.job_run_id)">刷新</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { getJobRun, resumeJobRun } from '../api/agent'
import { usePermission } from '@/common/composables/usePermission'
import type { JobRunDetail } from '../types'
import { statusLabel, statusTagType } from '../types/labels'

const { hasPerm } = usePermission()

const dialogVisible = ref(false)
const loading = ref(false)
const resuming = ref(false)
const run = ref<JobRunDetail | null>(null)
// 当前展开明细的步骤ID('' 表示全部收起)
const activeItemStep = ref('')

/** 断点续跑按钮: 失败/取消态且具备 skill:invoke 权限才可操作 */
const canResume = computed(() =>
  run.value != null
  && (run.value.status === 'failed' || run.value.status === 'cancelled')
  && hasPerm('agent:skill:invoke'),
)

/** 步骤状态表数据(steps_state 字典转行) */
const stepRows = computed(() =>
  Object.entries(run.value?.steps_state ?? {}).map(([id, state]) => ({ id, ...state })),
)

/** 展开项明细表数据(当前展开步骤的 items 字典转行) */
const itemRows = computed(() => {
  const state = run.value?.steps_state?.[activeItemStep.value]
  return Object.entries(state?.items ?? {}).map(([key, item]) => ({ key, item }))
})

/** 打开并加载运行详情 */
const open = async (jobRunId: string) => {
  dialogVisible.value = true
  activeItemStep.value = ''
  await load(jobRunId)
}
defineExpose({ open })

/** 拉取详情(刷新复用) */
const load = async (jobRunId?: string) => {
  if (!jobRunId) return
  try {
    loading.value = true
    run.value = await getJobRun(jobRunId)
  } catch (error) {
    console.error('获取 job 运行详情失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '获取详情失败')
  } finally {
    loading.value = false
  }
}

/** 断点续跑: 已成功项直接复用, 从失败/取消位置继续执行 */
const handleResume = async () => {
  const target = run.value
  if (!target) return
  try {
    resuming.value = true
    await resumeJobRun(target.job_run_id)
    ElMessage.success('已发起断点续跑')
    await load(target.job_run_id)
  } catch (error) {
    console.error('断点续跑失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '断点续跑失败')
  } finally {
    resuming.value = false
  }
}

const formatTime = (iso: string | null) => {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

/** JSON 美化(解析失败原样返回) */
const formatJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>
