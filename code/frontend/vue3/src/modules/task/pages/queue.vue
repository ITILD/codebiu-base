<template>
  <div p-3 md:p-4 w-full flex flex-col gap-3>
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

    <!-- 工具栏: 搜索 + 自动刷新 + 自愈 + 新建 -->
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
      <el-tooltip content="重派发重启遗留的排队任务 + 清扫无 worker 回写的僵尸执行任务" placement="top">
        <el-button :loading="recovering" @click="handleRecover">
          <el-icon mr-1><RefreshLeft /></el-icon>任务自愈
        </el-button>
      </el-tooltip>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon mr-1><Plus /></el-icon>新建任务
      </el-button>
    </div>

    <!-- 运维面板: Celery 执行器监控 + 任务类型入队优先级热调 -->
    <div rounded-note-md bg-note-card shadow-note>
      <el-collapse v-model="opsPanel">
        <el-collapse-item name="workers">
          <template #title>
            <div flex items-center gap-2 px-1>
              <span font-medium>Celery 执行器</span>
              <el-tag size="small" :type="workersData?.online ? 'success' : 'danger'" effect="light">
                在线 {{ workersData?.online ?? 0 }}/{{ workersData?.total ?? 0 }}
              </el-tag>
              <span v-if="workersData?.error" text-xs text-note-sub>{{ workersData.error }}</span>
            </div>
          </template>
          <div px-3 pb-3>
            <el-table v-if="workersData?.workers?.length" :data="workersData.workers" size="small">
              <el-table-column prop="name" label="执行器" min-width="150" show-overflow-tooltip />
              <el-table-column label="消费队列" min-width="130">
                <template #default="{ row }">
                  <el-tag v-for="q in row.queues" :key="q" size="small" effect="plain" class="mr-1">
                    {{ q }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="并发" prop="concurrency" width="70" align="center" />
              <el-table-column label="活跃" width="70" align="center">
                <template #default="{ row }">
                  <span :class="row.active > 0 ? 'text-note-green font-medium' : 'text-note-sub'">
                    {{ row.active }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="已处理" prop="processed" width="90" align="center" />
              <el-table-column label="PID" prop="pid" width="90" align="center" />
              <el-table-column label="正在执行" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.active_tasks?.length" text-xs>
                    {{ row.active_tasks.map((t: any) => t.name?.split('.').pop()).join('、') }}
                  </span>
                  <span v-else text-xs text-note-sub>空闲</span>
                </template>
              </el-table-column>
            </el-table>
            <el-empty
              v-else
              :description="workersData?.error ?? '没有执行器在线, 请启动 app_task.py worker'"
              :image-size="60"
            />
          </div>
        </el-collapse-item>
        <el-collapse-item name="priority">
          <template #title>
            <div flex items-center gap-2 px-1>
              <span font-medium>类型优先级</span>
              <span text-xs text-note-sub>0~9 越大越优先, ≥7 走交互队列; 立即生效, 仅影响之后创建的任务</span>
            </div>
          </template>
          <el-table :data="registry" size="small" px-3>
            <el-table-column label="任务类型" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.name }}</span>
                <el-tag v-if="row.priority_override != null" size="small" type="warning" effect="plain" class="ml-1">
                  已覆盖
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="default_priority" label="默认" width="70" align="center">
              <template #default="{ row }">
                <span text-note-sub>P{{ row.default_priority ?? 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column label="生效优先级" width="120" align="center">
              <template #default="{ row }">
                <el-select
                  :model-value="row.effective_priority ?? 0"
                  size="small"
                  :loading="prioritySaving === row.type"
                  @change="(val: number) => handlePriorityChange(row, val)"
                >
                  <el-option v-for="n in 10" :key="n" :value="n - 1" :label="`P${n - 1}`" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="消费队列" width="120" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.queue === 'q_interactive' ? 'warning' : 'info'" effect="plain">
                  {{ row.queue }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="row.priority_override != null"
                  link type="primary" size="small"
                  @click="handlePriorityChange(row, null)"
                >
                  恢复默认
                </el-button>
                <span v-else text-xs text-note-sub>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 批量操作条: 选中后出现 -->
    <div
      v-if="selectedRows.length"
      class="flex flex-wrap items-center gap-2 rounded-note-md bg-note-tint px-3 py-2"
    >
      <span text-sm text-note-green>已选 {{ selectedRows.length }} 项</span>
      <el-button size="small" :loading="batchBusy" @click="handleBatchCancel">批量取消</el-button>
      <el-button size="small" :loading="batchBusy" @click="handleBatchRetry">批量重试</el-button>
      <el-button size="small" type="danger" plain :loading="deleting" @click="handleBatchDelete">
        批量删除
      </el-button>
      <el-button class="ml-auto" link size="small" @click="clearSelection">取消选择</el-button>
    </div>

    <!-- 任务表格 -->
    <el-table
      ref="tableRef"
      :data="tableData"
      v-loading="loading"
      stripe
      w-full
      row-key="id"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="44" :fixed="isMd ? 'left' : false" />
      <el-table-column prop="name" label="任务名称" min-width="130" show-overflow-tooltip />
      <el-table-column label="类型" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          {{ typeName(row.task_type) }}
        </template>
      </el-table-column>
      <el-table-column label="优先级" width="80" align="center">
        <template #default="{ row }">
          <el-tooltip
            v-if="row.priority >= 7"
            content="高优先级, 路由交互队列 q_interactive"
            placement="top"
          >
            <el-tag size="small" type="warning" effect="plain">P{{ row.priority }}</el-tag>
          </el-tooltip>
          <span v-else text-xs text-note-sub>P{{ row.priority }}</span>
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
        small
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
import { Plus, RefreshLeft } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type TableInstance } from 'element-plus'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { useBatchDelete } from '@/common/composables/useBatchDelete'
import {
  cancelTask,
  deleteTask,
  getTaskRegistry,
  getTaskStats,
  getTaskWorkers,
  listTasks,
  recoverTasks,
  retryTask,
  updateTaskTypePriority,
} from '../api/task'
import {
  statusLabels,
  statusOptions,
  statusTagTypes,
  type QueueTask,
  type TaskStats,
  type TaskStatus,
  type TaskTypeDef,
  type TaskWorkerList,
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

// ################ 运维面板: 执行器监控 + 优先级热调 + 手动自愈 ################
const opsPanel = ref<string[]>(['workers'])
const workersData = ref<TaskWorkerList | null>(null)

/** 采集 Celery 执行器状态(broker 不可用返回 online=0, 不抛错) */
const fetchWorkers = async () => {
  try {
    workersData.value = await getTaskWorkers()
  }
  catch (error) {
    console.error('获取执行器状态失败:', error)
  }
}

/** 优先级热调(P0~P9; null=清除覆盖恢复默认), 成功后以响应单条刷新注册表行 */
const prioritySaving = ref('')
const handlePriorityChange = async (row: TaskTypeDef, val: number | null) => {
  prioritySaving.value = row.type
  try {
    const updated = await updateTaskTypePriority(row.type, val)
    const idx = registry.value.findIndex(t => t.type === row.type)
    if (idx >= 0) registry.value[idx] = { ...registry.value[idx], ...updated }
    ElMessage.success(
      val == null ? `已恢复「${row.name}」默认优先级` : `「${row.name}」生效优先级已调整为 P${val}`,
    )
  }
  catch (error) {
    console.error('调整优先级失败:', error)
    ElMessage.error('调整优先级失败')
  }
  finally {
    prioritySaving.value = ''
  }
}

/** 手动自愈(重派发遗留 PENDING + 清扫僵尸 RUNNING) */
const recovering = ref(false)
const handleRecover = async () => {
  recovering.value = true
  try {
    const result = await recoverTasks()
    ElMessage.success(`自愈完成: 重派发 ${result.recovered} 项, 清扫僵尸 ${result.reaped} 项`)
    await refreshAll()
  }
  catch (error) {
    console.error('任务自愈失败:', error)
    ElMessage.error('任务自愈失败')
  }
  finally {
    recovering.value = false
  }
}

// ################ 列表与查询(统一使用 useTableQuery) ################
// 搜索字段配置(名称/类型/状态/优先级)
const searchFields: SearchField[] = [
  { prop: 'keyword', label: '名称' },
  {
    prop: 'task_type', label: '类型', type: 'select',
    options: [], // 挂载后由注册表填充
  },
  { prop: 'status', label: '状态', type: 'select', options: statusOptions },
  {
    prop: 'priority', label: '优先级', type: 'select',
    options: Array.from({ length: 10 }, (_, i) => ({ label: `P${i}`, value: i })),
  },
]

// 分页/查询参数/表格数据/拉取/末页回退统一收口
const {
  pagination, queryParams, tableData, total, loading,
  fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<QueueTask>(async (params) => {
  const { keyword, task_type, status, priority } = params
  // 空值不传递; 局部变量中转避免 TS excess property check
  const query = {
    ...params,
    keyword: (keyword as string) || undefined,
    task_type: (task_type as string) || undefined,
    status: (status as string) || undefined,
    priority: priority ?? undefined,
  }
  return listTasks(query)
}, { defaultQuery: { keyword: '', task_type: undefined, status: undefined, priority: undefined } })

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
// 执行器监控独立 30 秒低频采集(inspect 有秒级延迟, 不适合高频)
watch([autoRefresh, hasActive], setupPolling, { immediate: true })

let workerTimer: number | undefined

function setupPolling() {
  window.clearInterval(pollTimer)
  window.clearInterval(workerTimer)
  pollTimer = undefined
  workerTimer = undefined
  if (!autoRefresh.value) return
  const interval = hasActive.value ? 3000 : 10000
  pollTimer = window.setInterval(() => {
    // 活跃期间整表刷新, 空闲时仅刷统计(降低数据库压力)
    // 有选中行时暂停整表刷新, 避免轮询清空用户的多选状态
    if (hasActive.value && !selectedRows.value.length) fetchData()
    else fetchStats()
  }, interval)
  workerTimer = window.setInterval(fetchWorkers, 30_000)
}

onBeforeUnmount(() => {
  window.clearInterval(pollTimer)
  window.clearInterval(workerTimer)
})

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

// ################ 批量操作 ################
const tableRef = ref<TableInstance>()
const selectedRows = ref<QueueTask[]>([])
const { batchDelete, deleting } = useBatchDelete()
const batchUpdating = ref(false)
const batchBusy = computed(() => deleting.value || batchUpdating.value)

/** 多选变化 */
const handleSelectionChange = (rows: QueueTask[]) => {
  selectedRows.value = rows
}

/** 清空多选 */
const clearSelection = () => {
  tableRef.value?.clearSelection()
  selectedRows.value = []
}

/** 批量结果汇总提示 */
const notifyBatchResult = (results: PromiseSettledResult<unknown>[], action: string) => {
  const ok = results.filter(r => r.status === 'fulfilled').length
  const failed = results.length - ok
  if (ok) ElMessage.success(`已${action} ${ok} 项${failed ? `，${failed} 项失败` : ''}`)
  if (failed) ElMessage.error(`${failed} 项${action}失败`)
}

/** 批量取消(仅排队/执行中可取消) */
const handleBatchCancel = async () => {
  const targets = selectedRows.value.filter(r => ['pending', 'running'].includes(r.status))
  if (!targets.length) {
    ElMessage.warning('选中任务中没有可取消的任务')
    return
  }
  try {
    await ElMessageBox.confirm(`确定取消选中的 ${targets.length} 个任务吗?`, '批量取消', {
      type: 'warning', confirmButtonText: '取消任务', cancelButtonText: '返回',
    })
  } catch {
    return
  }
  batchUpdating.value = true
  try {
    const results = await Promise.allSettled(targets.map(t => cancelTask(t.id)))
    notifyBatchResult(results, '取消')
    await refreshAll()
    clearSelection()
  } finally {
    batchUpdating.value = false
  }
}

/** 批量重试(仅已结束任务可重试) */
const handleBatchRetry = async () => {
  const targets = selectedRows.value.filter(r => isFinished(r))
  if (!targets.length) {
    ElMessage.warning('选中任务中没有可重试的任务')
    return
  }
  try {
    await ElMessageBox.confirm(`确定重试选中的 ${targets.length} 个任务吗?`, '批量重试', {
      type: 'info', confirmButtonText: '重试', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  batchUpdating.value = true
  try {
    const results = await Promise.allSettled(targets.map(t => retryTask(t.id)))
    notifyBatchResult(results, '重试')
    await refreshAll()
    clearSelection()
  } finally {
    batchUpdating.value = false
  }
}

/** 批量删除(逐条调用删除接口并汇总结果) */
const handleBatchDelete = async () => {
  const removed = await batchDelete({
    rows: selectedRows.value,
    getId: row => row.id,
    remove: id => deleteTask(String(id)),
    label: row => row.name,
    onRemoved: async (n) => {
      await Promise.all([refreshAfterRemove(n), fetchStats()])
    },
  })
  if (removed) clearSelection()
}

// ################ 生命周期 ################
onMounted(async () => {
  // 任务类型注册表/执行器状态/统计为独立请求, 并行拉取(串行等待会叠加首屏时间)
  // 加载任务类型注册表(搜索下拉 + 新建对话框 + 优先级热调表), 失败仅降级下拉选项
  getTaskRegistry()
    .then((r) => {
      registry.value = r
      searchFields[1].options = r.map(t => ({ label: t.name, value: t.type }))
    })
    .catch((error) => {
      console.error('获取任务类型注册表失败:', error)
    })
  fetchWorkers()
  // 列表已由 useTableQuery 自动拉取, 此处补充刷新统计
  await fetchStats()
})
</script>
