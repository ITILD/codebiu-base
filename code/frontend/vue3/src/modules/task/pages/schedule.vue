<template>
  <div p-4 md:p-6 w-full flex flex-col gap-4>
    <!-- 水墨页头 -->
    <InkPageHead title="定时任务" sub="周期调度的定义与执行触发" seal="时" />

    <!-- 工具栏: 搜索 + 新建 -->
    <div flex flex-wrap items-center gap-3>
      <TableSearchBar
        v-model="queryParams"
        :fields="searchFields"
        :collapse-count="2"
        @search="handleSearch"
        @reset="handleSearch"
      />
      <div flex-1 />
      <el-button type="primary" @click="openCreate">
        <el-icon mr-1><Plus /></el-icon>新建调度
      </el-button>
    </div>

    <!-- 调度表格 -->
    <el-table :data="tableData" v-loading="loading" stripe w-full>
      <el-table-column prop="name" label="调度名称" min-width="150" show-overflow-tooltip />
      <el-table-column label="任务类型" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          {{ typeName(row.task_type) }}
        </template>
      </el-table-column>
      <el-table-column label="触发周期" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.cron" font-mono text-xs>{{ row.cron }}</span>
          <span v-else text-xs>每 {{ intervalLabel(row.interval_seconds) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="启用" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            :loading="togglingId === row.id"
            @change="handleToggle(row, $event as boolean)"
          />
        </template>
      </el-table-column>
      <el-table-column label="下次触发" min-width="105" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatTime(row.next_fire_at, true) }}
        </template>
      </el-table-column>
      <el-table-column label="最近执行" min-width="105" show-overflow-tooltip>
        <template #default="{ row }">
          <div v-if="row.last_fired_at" flex flex-col gap-0.5>
            <span text-xs>{{ formatTime(row.last_fired_at, true) }}</span>
            <el-tag
              size="small" effect="light"
              :type="row.last_status === 'ok' ? 'success' : 'danger'"
            >
              {{ row.last_status === 'ok' ? '已派发' : '派发失败' }}
            </el-tag>
          </div>
          <span v-else text-xs text-note-sub>未执行</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.remark ?? '-' }}
        </template>
      </el-table-column>
      <!-- 操作列: 平板及以上固定右侧, 手机取消固定避免遮挡 -->
      <el-table-column label="操作" min-width="200" align="center" :fixed="isMd ? 'right' : false">
        <template #default="{ row }">
          <el-button link type="success" size="small" @click="handleTrigger(row)">立即触发</el-button>
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
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

    <!-- 新增/编辑对话框(子组件自持状态, open 时重置) -->
    <ScheduleEditDialog ref="editDialogRef" :registry="registry" :presets="presets" @saved="fetchData" />
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { useResponsive } from '@/common/composables/useResponsive'
import {
  deleteSchedule,
  getCronPresets,
  listSchedules,
  triggerSchedule,
  updateSchedule,
} from '../api/schedule'
import { getTaskRegistry } from '../api/task'
import type { CronPreset, TaskSchedule, TaskTypeDef } from '../types'
import ScheduleEditDialog from '../components/ScheduleEditDialog.vue'

// 响应式: 平板及以上操作列固定右侧
const { isMd } = useResponsive()

// ################ 类型注册表与 cron 预置 ################
const registry = ref<TaskTypeDef[]>([])
const presets = ref<CronPreset[]>([])

/** 类型编码转显示名 */
const typeName = (type: string) => registry.value.find(t => t.type === type)?.name ?? type

// ################ 列表查询(统一 useTableQuery) ################
const searchFields: SearchField[] = [
  { prop: 'keyword', label: '名称' },
  { prop: 'task_type', label: '类型', type: 'select', options: [] },
  {
    prop: 'enabled', label: '状态', type: 'select',
    options: [
      { label: '启用', value: 'true' },
      { label: '停用', value: 'false' },
    ],
  },
]

const {
  pagination, queryParams, tableData, total, loading,
  fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<TaskSchedule>(async (params) => {
  const { keyword, task_type, enabled } = params
  const query = {
    ...params,
    keyword: (keyword as string) || undefined,
    task_type: (task_type as string) || undefined,
    enabled: enabled === 'true' ? true : enabled === 'false' ? false : undefined,
  }
  return listSchedules(query)
}, { defaultQuery: { keyword: '', task_type: undefined, enabled: undefined } })

// ################ 行操作 ################

/** 间隔秒数人性化 */
const intervalLabel = (seconds: number | null) => {
  if (!seconds) return '-'
  if (seconds % 86400 === 0) return `${seconds / 86400} 天`
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`
  if (seconds % 60 === 0) return `${seconds / 60} 分钟`
  return `${seconds} 秒`
}

/** 时间格式化(UTC 转本地展示) */
const formatTime = (value: string | null | undefined, withDate = false) => {
  if (!value) return '-'
  const opt: Intl.DateTimeFormatOptions = withDate
    ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }
    : { hour: '2-digit', minute: '2-digit' }
  return new Date(value).toLocaleString('zh-CN', opt)
}

/** 启停切换中行ID(按钮 loading) */
const togglingId = ref<number | null>(null)

/** 启停切换(热生效: 后端重算下次触发并唤醒调度循环) */
const handleToggle = async (row: TaskSchedule, enabled: boolean) => {
  togglingId.value = row.id
  try {
    await updateSchedule(row.id, {
      name: row.name,
      task_type: row.task_type,
      payload: row.payload ?? {},
      cron: row.cron,
      interval_seconds: row.interval_seconds,
      enabled,
      remark: row.remark,
    })
    ElMessage.success(enabled ? '调度已启用(热生效)' : '调度已停用')
    await fetchData()
  }
  catch (error) {
    console.error('切换调度状态失败:', error)
    ElMessage.error('切换失败')
  }
  finally {
    togglingId.value = null
  }
}

/** 立即触发一次(不影响周期节奏) */
const handleTrigger = (row: TaskSchedule) => {
  ElMessageBox.confirm(
    `立即触发「${row.name}」一次? 不影响原有周期节奏。`,
    '触发确认',
    { type: 'info', confirmButtonText: '触发', cancelButtonText: '取消' },
  )
    .then(async () => {
      try {
        const result = await triggerSchedule(row.id)
        ElMessage.success(`已触发, 任务ID: ${result.task_id.slice(0, 8)}…(详情见任务列表)`)
        await fetchData()
      }
      catch (error) {
        console.error('触发调度失败:', error)
        ElMessage.error('触发失败')
      }
    })
    .catch(() => {})
}

/** 删除调度(确认后删除; 已派生任务不受影响) */
const handleDelete = (row: TaskSchedule) => {
  ElMessageBox.confirm(
    `确定删除调度「${row.name}」吗? 已派生的任务记录不受影响。`,
    '删除确认',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
    .then(async () => {
      try {
        await deleteSchedule(row.id)
        ElMessage.success('删除成功')
        await refreshAfterRemove()
      }
      catch (error) {
        console.error('删除调度失败:', error)
        ElMessage.error('删除调度失败')
      }
    })
    .catch(() => {})
}

// ################ 对话框编排 ################
const editDialogRef = ref<InstanceType<typeof ScheduleEditDialog>>()

const openCreate = () => editDialogRef.value?.open()
const openEdit = (row: TaskSchedule) => editDialogRef.value?.openEdit(row)

// ################ 生命周期 ################
onMounted(async () => {
  // 注册表与 cron 预置并行加载(搜索下拉 + 对话框共用)
  try {
    const [reg, preset] = await Promise.all([getTaskRegistry(), getCronPresets()])
    registry.value = reg
    presets.value = preset
    searchFields[1].options = reg.map(t => ({ label: t.name, value: t.type }))
  }
  catch (error) {
    console.error('加载任务类型注册表失败:', error)
  }
})
</script>
