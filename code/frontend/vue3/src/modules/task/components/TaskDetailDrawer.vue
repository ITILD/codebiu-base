<template>
  <!-- 任务详情抽屉(参数/结果 JSON + Celery 对照); 手机按屏宽自适应 -->
  <el-drawer v-model="visible" title="任务详情" :size="isMd ? '420px' : '92%'">
    <template v-if="detailTask">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="ID">
          <span break-all font-mono text-xs>{{ detailTask.id }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="名称">{{ detailTask.name }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ typeName(detailTask.task_type) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTagTypes[detailTask.status] ?? 'info'" size="small">
            {{ statusLabels[detailTask.status] ?? detailTask.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="进度">
          <el-progress
            :percentage="Math.round(detailTask.progress)"
            :stroke-width="10"
            :status="progressStatus(detailTask.status)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="当前阶段">{{ detailTask.message ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="Celery 对照">
          {{ detailTask.celery_state ?? '-' }}
          <span v-if="detailTask.celery_progress != null">/ {{ Math.round(detailTask.celery_progress) }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="Celery ID">
          <span break-all font-mono text-xs>{{ detailTask.celery_task_id ?? '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(detailTask.created_at, true) }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ formatTime(detailTask.started_at, true) }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ formatTime(detailTask.finished_at, true) }}</el-descriptions-item>
      </el-descriptions>

      <!-- 失败原因 -->
      <el-alert
        v-if="detailTask.error" type="error" :closable="false" show-icon mt-3
        :title="detailTask.error"
      />

      <!-- 操作区: 取消/重试/同步校正(worker 回写中断时使用) -->
      <div flex justify-end gap-2 mt-2>
        <el-button
          v-if="detailTask.status === 'pending' || detailTask.status === 'running'"
          size="small" text type="warning" @click="handleCancel"
        >
          取消任务
        </el-button>
        <el-button
          v-if="isFinished(detailTask)"
          size="small" text type="primary" @click="handleRetry"
        >
          重试任务
        </el-button>
        <el-button size="small" text type="primary" :loading="submitting" @click="handleSync">
          从 Celery 同步状态
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { cancelTask, getTask, retryTask, syncTask } from '../api/task'
import { statusLabels, statusTagTypes, type QueueTask, type TaskStatus, type TaskTypeDef } from '../types'
import { useResponsive } from '@/common/composables/useResponsive'

// 响应式: 手机端抽屉按屏宽自适应
const { isMd } = useResponsive()

// 任务类型注册表(类型编码转显示名; 由父级编排层加载后传入)
const props = defineProps<{ registry: TaskTypeDef[] }>()
// 取消/重试/同步成功后通知父级刷新列表与统计
const emit = defineEmits<{ changed: [] }>()

/** 类型编码转显示名 */
const typeName = (type: string) => props.registry.find(t => t.type === type)?.name ?? type

/** 任务是否已结束(可重试) */
const isFinished = (row: QueueTask) =>
  !['pending', 'running'].includes(row.status)

/** 进度条状态色 */
const progressStatus = (status: TaskStatus) =>
  status === 'success' ? 'success' : status === 'failed' ? 'exception' : undefined

/** 时间格式化 */
const formatTime = (value: string | null | undefined, withDate = false) => {
  if (!value) return '-'
  const opt: Intl.DateTimeFormatOptions = withDate
    ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }
    : { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
  return new Date(value).toLocaleString('zh-CN', opt)
}

const visible = ref(false)
// 当前展示的任务详情
const detailTask = ref<QueueTask | null>(null)
// 同步状态的提交中标志
const submitting = ref(false)

/** 打开详情抽屉(open(row) 接收行数据, 拉取最新进度) */
const open = async (row: QueueTask) => {
  try {
    detailTask.value = await getTask(row.id)
    visible.value = true
  }
  catch (error) {
    console.error('获取任务详情失败:', error)
    ElMessage.error('获取任务详情失败')
  }
}

/** 从 Celery 结果后端同步状态 */
const handleSync = async () => {
  if (!detailTask.value) return
  try {
    submitting.value = true
    detailTask.value = await syncTask(detailTask.value.id)
    ElMessage.success('状态已同步')
    emit('changed')
  }
  catch (error) {
    console.error('同步状态失败:', error)
    ElMessage.error('同步状态失败')
  }
  finally {
    submitting.value = false
  }
}

/** 取消任务(确认后 revoke + 置 cancelled) */
const handleCancel = () => {
  const task = detailTask.value
  if (!task) return
  ElMessageBox.confirm(`确定取消任务「${task.name}」吗?`, '取消确认', {
    type: 'warning', confirmButtonText: '取消任务', cancelButtonText: '返回',
  })
    .then(async () => {
      try {
        await cancelTask(task.id)
        ElMessage.success('任务已取消')
        // 回读最新状态并通知父级刷新列表
        detailTask.value = await getTask(task.id)
        emit('changed')
      }
      catch (error) {
        console.error('取消任务失败:', error)
        ElMessage.error('取消任务失败')
      }
    })
    .catch(() => {})
}

/** 重试任务(重置进度重新入队) */
const handleRetry = async () => {
  if (!detailTask.value) return
  try {
    // 重试接口返回重置后的最新任务
    detailTask.value = await retryTask(detailTask.value.id)
    ElMessage.success('任务已重新入队')
    emit('changed')
  }
  catch (error) {
    console.error('重试任务失败:', error)
    ElMessage.error('重试任务失败')
  }
}

defineExpose({ open })
</script>
