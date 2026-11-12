<!-- 调用记录详情对话框: 统一信封观测口径(输入摘要/输出/错误/耗时, REQ-018) -->
<template>
  <el-dialog v-model="dialogVisible" title="调用记录详情" width="92%" class="max-w-[640px]">
    <div v-loading="loading" min-h-40>
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="调用ID" :span="2">{{ detail.invocation_id }}</el-descriptions-item>
          <el-descriptions-item label="技能键">{{ detail.skill_key }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detail.skill_version ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">{{ statusLabel(detail.status) }}</el-tag>
            <el-tag v-if="detail.degraded" type="warning" size="small" ml-1>降级</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="形态">{{ detail.mode }} · {{ detail.entry ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="耗时">
            {{ detail.duration_ms != null ? `${detail.duration_ms} ms` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="tokens">{{ detail.tokens ?? '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.task_id" label="队列任务" :span="2">{{ detail.task_id }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatTime(detail.finished_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detail.error_class" label="错误类型" :span="2">
            <span class="text-[var(--el-color-danger)]">{{ detail.error_class }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.error_message" label="错误信息" :span="2">
            {{ detail.error_message }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.input_summary" mt-3>
          <div text-xs text-note-sub mb-1>输入摘要</div>
          <pre class="m-0 p-2 text-xs rounded bg-[var(--el-fill-color-light)] overflow-auto max-h-50
            whitespace-pre-wrap break-all">{{ formatJson(detail.input_summary) }}</pre>
        </div>
        <div v-if="detail.output" mt-2>
          <div text-xs text-note-sub mb-1>输出(截断口径)</div>
          <pre class="m-0 p-2 text-xs rounded bg-[var(--el-fill-color-light)] overflow-auto max-h-80
            whitespace-pre-wrap break-all">{{ formatJson(detail.output) }}</pre>
        </div>
      </template>
    </div>
    <template #footer>
      <span>
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="loading" @click="load(detail?.invocation_id)">刷新</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { getInvocation } from '../api/agent'
import type { InvocationDetail } from '../types'
import { statusLabel, statusTagType } from '../types/labels'

const dialogVisible = ref(false)
const loading = ref(false)
const detail = ref<InvocationDetail | null>(null)

/** 打开并加载详情 */
const open = async (invocationId: string) => {
  dialogVisible.value = true
  await load(invocationId)
}
defineExpose({ open })

/** 拉取详情(刷新复用) */
const load = async (invocationId?: string) => {
  if (!invocationId) return
  try {
    loading.value = true
    detail.value = await getInvocation(invocationId)
  } catch (error) {
    console.error('获取调用详情失败:', error)
  } finally {
    loading.value = false
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
