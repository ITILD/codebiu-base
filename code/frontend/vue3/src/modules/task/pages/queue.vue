<template>
  <div p-4 md:p-6 w-full flex flex-col gap-4>
    <!-- 水墨页头 -->
    <InkPageHead title="任务队列" sub="后台任务的执行与重试记录" seal="队" />

    <!-- 状态统计卡片(轮询刷新): 手机 2 列 / 平板及以上 4 列 -->
    <div grid grid-cols-2 md:grid-cols-4 gap-3>
      <div
        v-for="card in statCards" :key="card.status"
        cursor-pointer rounded-lg p-3
        bg-note-card shadow-note
        transition-colors hover:bg-note-tint
        :class="{ 'ring-2 ring-note': queryParams.status === card.status }"
        @click="handleStatCardClick(card.status)"
      >
        <div text-xs text-note-sub>{{ card.label }}</div>
        <div text-2xl font-bold mt-1 :class="card.color">{{ card.value }}</div>
      </div>
    </div>

    <!-- 工具栏: 搜索 + 自动刷新 + 新建 -->
    <div flex flex-wrap items-center gap-3>
      <TableSearchBar
        v-model="queryParams"
        :fields="searchFields"
        :collapse-count="2"
        @search="handleSearch"
        @reset="handleSearch"
      />
      <el-tooltip content="存在活跃任务时每 3 秒自动刷新状态与进度" placement="top">
        <div flex items-center gap-1>
          <span text-xs text-note-sub>自动刷新</span>
          <el-switch v-model="autoRefresh" />
        </div>
      </el-tooltip>
      <div flex-1 />
      <el-button type="primary" @click="openCreateDialog">
        <el-icon mr-1><Plus /></el-icon>新建任务
      </el-button>
    </div>

    <!-- 任务表格 -->
    <el-table :data="tableData" v-loading="loading" stripe w-full>
      <el-table-column prop="name" label="任务名称" min-width="130" show-overflow-tooltip />
      <el-table-column label="类型" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          {{ typeName(row.task_type) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagTypes[row.status as TaskStatus] ?? 'info'" size="small" effect="light">
            {{ statusLabels[row.status as TaskStatus] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- 完成百分比(轮询实时推进) -->
      <el-table-column label="进度" min-width="170">
        <template #default="{ row }">
          <div flex items-center gap-2>
            <el-progress
              class="flex-1"
              :percentage="Math.round(row.progress)"
              :stroke-width="8"
              :status="progressStatus(row.status)"
            />
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="message" label="当前阶段" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.message ?? '-' }}
        </template>
      </el-table-column>
      <!-- Celery 侧状态对照(broker/backend 真实状态) -->
      <el-table-column label="Celery" min-width="100" align="center">
        <template #default="{ row }">
          <el-tooltip v-if="row.celery_progress != null" :content="`Celery 侧进度 ${row.celery_progress}%`" placement="top">
            <span text-xs>{{ row.celery_state ?? '-' }} {{ Math.round(row.celery_progress) }}%</span>
          </el-tooltip>
          <span v-else text-xs text-note-sub>{{ row.celery_state ?? '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="100" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <!-- 操作列: 平板及以上固定右侧, 手机取消固定避免遮挡 -->
      <el-table-column label="操作" min-width="190" align="center" :fixed="isMd ? 'right' : false">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          <el-button
            v-if="row.status === 'pending' || row.status === 'running'"
            link type="warning" size="small" @click="handleCancel(row)"
          >
            取消
          </el-button>
          <el-button
            v-if="isFinished(row)"
            link type="primary" size="small" @click="handleRetry(row)"
          >
            重试
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div flex justify-end>
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.size"
        :total="total"
        layout="total, prev, pager, next"
        @size-change="fetchData"
        @current-change="fetchData"
      />
    </div>

    <!-- 新建任务对话框(子组件自持状态, open 时重置) -->
    <TaskCreateDialog ref="createDialogRef" :registry="registry" @saved="refreshAll" />

    <!-- 任务详情抽屉(子组件 open(row) 拉取最新数据, 取消/重试/同步后通知刷新) -->
    <TaskDetailDrawer ref="detailDrawerRef" :registry="registry" @changed="refreshAll" />
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import { useTableQuery } from '@/common/composables/useTableQuery'
import {
  cancelTask,
  deleteTask,
  getTaskRegistry,
  getTaskStats,
  listTasks,
  retryTask,
} from '../api/task'
import {
  statusLabels,
  statusOptions,
  statusTagTypes,
  type QueueTask,
  type TaskStats,
  type TaskStatus,
  type TaskTypeDef,
} from '../types'
import { useResponsive } from '@/common/composables/useResponsive'
import TaskCreateDialog from '../components/TaskCreateDialog.vue'
import TaskDetailDrawer from '../components/TaskDetailDrawer.vue'

// 响应式: 平板及以上操作列固定右侧
const { isMd } = useResponsive()

// ################ 统计概览 ################
const stats = ref<TaskStats>({ total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0 })

/** 概览卡片配置(点击可按状态筛选) */
const statCards = computed(() => [
  { status: '', label: '全部任务', value: stats.value.total, color: 'text-note' },
  { status: 'pending', label: '排队中', value: stats.value.pending, color: 'text-note-sub' },
  { status: 'running', label: '执行中', value: stats.value.running, color: 'text-blue-500' },
  { status: 'success', label: '成功', value: stats.value.success, color: 'text-green-600' },
  { status: 'failed', label: '失败', value: stats.value.failed, color: 'text-red-500' },
  { status: 'cancelled', label: '已取消', value: stats.value.cancelled, color: 'text-orange-400' },
])

/** 点击统计卡片: 切换状态过滤并刷新 */
const handleStatCardClick = (status: string) => {
  queryParams.value.status = status || undefined
  pagination.value.page = 1
  fetchData()
}

// ################ 类型注册表 ################
const registry = ref<TaskTypeDef[]>([])

/** 类型编码转显示名 */
const typeName = (type: string) => registry.value.find(t => t.type === type)?.name ?? type

// ################ 列表与查询(统一使用 useTableQuery) ################
// 搜索字段配置(名称/类型/状态)
const searchFields: SearchField[] = [
  { prop: 'keyword', label: '名称' },
  {
    prop: 'task_type', label: '类型', type: 'select',
    options: [], // 挂载后由注册表填充
  },
  { prop: 'status', label: '状态', type: 'select', options: statusOptions },
]

// 分页/查询参数/表格数据/拉取/末页回退统一收口
const {
  pagination, queryParams, tableData, total, loading,
  fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<QueueTask>(async (params) => {
  const { keyword, task_type, status } = params
  // 空值不传递; 局部变量中转避免 TS excess property check
  const query = {
    ...params,
    keyword: (keyword as string) || undefined,
    task_type: (task_type as string) || undefined,
    status: (status as string) || undefined,
  }
  return listTasks(query)
}, { defaultQuery: { keyword: '', task_type: undefined, status: undefined } })

/** 获取状态统计 */
const fetchStats = async () => {
  try {
    stats.value = await getTaskStats()
  }
  catch (error) {
    console.error('获取任务统计失败:', error)
  }
}

/** 刷新列表 + 统计 */
const refreshAll = async () => {
  await Promise.all([fetchData(), fetchStats()])
}

// ################ 轮询 ################
const autoRefresh = ref(true)
let pollTimer: number | undefined

/** 是否存在活跃任务(排队/执行中) */
const hasActive = computed(() =>
  tableData.value.some(t => t.status === 'pending' || t.status === 'running'),
)

// 自动刷新开关: 活跃期间每 3 秒轮询(无活跃任务时自动降频到 10 秒仅刷统计)
watch([autoRefresh, hasActive], setupPolling, { immediate: true })

function setupPolling() {
  window.clearInterval(pollTimer)
  pollTimer = undefined
  if (!autoRefresh.value) return
  const interval = hasActive.value ? 3000 : 10000
  pollTimer = window.setInterval(() => {
    // 活跃期间整表刷新, 空闲时仅刷统计(降低数据库压力)
    if (hasActive.value) fetchData()
    else fetchStats()
  }, interval)
}

onBeforeUnmount(() => window.clearInterval(pollTimer))

// ################ 对话框/抽屉子组件编排(状态自持, open 时重置防脏数据) ################
const createDialogRef = ref<InstanceType<typeof TaskCreateDialog>>()
const detailDrawerRef = ref<InstanceType<typeof TaskDetailDrawer>>()

/** 打开新建任务对话框 */
const openCreateDialog = () => createDialogRef.value?.open()

/** 打开任务详情抽屉(子组件拉取最新数据) */
const openDetail = (row: QueueTask) => detailDrawerRef.value?.open(row)

// ################ 行操作 ################

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

/** 取消任务(确认后 revoke + 置 cancelled) */
const handleCancel = (row: QueueTask) => {
  ElMessageBox.confirm(`确定取消任务「${row.name}」吗?`, '取消确认', {
    type: 'warning', confirmButtonText: '取消任务', cancelButtonText: '返回',
  })
    .then(async () => {
      try {
        await cancelTask(row.id)
        ElMessage.success('任务已取消')
        await refreshAll()
      }
      catch (error) {
        console.error('取消任务失败:', error)
        ElMessage.error('取消任务失败')
      }
    })
    .catch(() => {})
}

/** 重试任务(重置进度重新入队) */
const handleRetry = async (row: QueueTask) => {
  try {
    await retryTask(row.id)
    ElMessage.success('任务已重新入队')
    await refreshAll()
  }
  catch (error) {
    console.error('重试任务失败:', error)
    ElMessage.error('重试任务失败')
  }
}

/** 删除任务(确认后删除记录) */
const handleDelete = (row: QueueTask) => {
  ElMessageBox.confirm(
    `确定删除任务「${row.name}」吗? 删除后不可恢复。`,
    '删除确认',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
    .then(async () => {
      try {
        await deleteTask(row.id)
        ElMessage.success('删除成功')
        // 删除后末行回退翻页统一由 useTableQuery 处理, 并同步统计
        await Promise.all([refreshAfterRemove(), fetchStats()])
      }
      catch (error) {
        console.error('删除任务失败:', error)
        ElMessage.error('删除任务失败')
      }
    })
    .catch(() => {})
}

// ################ 生命周期 ################
onMounted(async () => {
  // 任务类型注册表与统计为独立请求, 并行拉取(串行等待会叠加首屏时间)
  // 加载任务类型注册表(搜索下拉 + 新建对话框), 失败仅降级下拉选项
  getTaskRegistry()
    .then((r) => {
      registry.value = r
      searchFields[1].options = r.map(t => ({ label: t.name, value: t.type }))
    })
    .catch((error) => {
      console.error('获取任务类型注册表失败:', error)
    })
  // 列表已由 useTableQuery 自动拉取, 此处补充刷新统计
  await fetchStats()
})
</script>
