<template>
  <div p-4 md:p-6 w-full>
    <!-- 水墨页头 -->
    <InkPageHead title="模型配置" sub="对话 / 向量 / 重排 / 语音, 各安其位" seal="芯" />

    <!-- 统一搜索栏: 多字段筛选 -->
    <TableSearchBar
      v-model="queryParams"
      :fields="searchFields"
      @search="handleSearch"
      @reset="handleSearch"
    >
      <template #actions>
        <el-button v-if="isAdmin" type="warning" plain :loading="revectorizing" @click="handleRevectorize">
          重建向量索引
        </el-button>
        <el-button type="primary" @click="handleCreate">新增模型配置</el-button>
      </template>
    </TableSearchBar>

    <!-- 数据表格(不生效模型整行灰显) -->
    <el-table :data="tableData" v-loading="loading" stripe w-full :row-class-name="inactiveRowClass">
      <el-table-column label="模型类型" min-width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="modelTypeTagType[row.model_type] ?? 'info'" size="small">
            {{ modelTypeLabel(row.model_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="服务方案" min-width="130" align="center">
        <template #default="{ row }">
          {{ serverTypeLabel(row.server_type) }}
        </template>
      </el-table-column>
      <el-table-column label="模型" min-width="200">
        <template #default="{ row }">
          <div flex flex-col>
            <div flex items-center gap-1>
              <span>{{ modelMainLabel(row) }}</span>
              <el-tag v-if="row.is_default" type="warning" size="small">默认</el-tag>
              <el-tag v-if="row.is_active === false" type="info" size="small">不生效</el-tag>
              <!-- 能力标签: 最近一次测试结果持久化展示(通过=绿色, 失败=红色, 仅颜色区分); 未测试过回退旧校验字段 -->
              <template v-if="row.check_result">
                <el-tooltip v-for="cap in testedCapabilities(row)" :key="cap.key"
                  :content="cap.ok ? (cap.detail || '测试通过') : (cap.error || '测试未通过')" placement="top">
                  <el-tag :type="cap.ok ? 'success' : 'danger'" size="small" effect="light">
                    {{ cap.label }}
                  </el-tag>
                </el-tooltip>
              </template>
              <template v-else>
                <el-tag v-if="row.check_valid === true" type="success" size="small">校验通过</el-tag>
                <el-tag v-else-if="row.check_valid === false" type="danger" size="small">校验失败</el-tag>
              </template>
            </div>
            <div v-if="row.display_name && row.display_name !== row.model" text-xs text-note-sub>
              {{ row.model }}
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="URL" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <!-- url/api_key: 管理员可见明文; 其他用户仅本人私有模型保留明文, 其余脱敏 -->
          {{ row.url || '已脱敏' }}
        </template>
      </el-table-column>
      <el-table-column label="归属" min-width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="scopeTagType[row.scope] ?? 'info'" size="small">
            {{ scopeShortLabel(row.scope) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatTimeShort(row.updated_at) }}
        </template>
      </el-table-column>
      <!-- 操作列: 平板及以上固定右侧, 手机取消固定避免遮挡 -->
      <el-table-column label="操作" min-width="180" align="center" :fixed="isMd ? 'right' : false">
        <template #default="{ row }">
          <!-- 测试: 任意可见模型均可发起(公共/部门/本人) -->
          <el-button link type="success" size="small" @click="handleTest(row)">
            测试
          </el-button>
          <template v-if="canManage(row)">
            <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
          <span v-else text-xs text-note-sub>仅查看</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页(手机居中, 桌面靠右) -->
    <div mt-4 flex flex-wrap justify-center sm:justify-end>
      <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
        :total="total" layout="total, prev, pager, next"
        @size-change="fetchData" @current-change="fetchData" />
    </div>

    <!-- 编辑/创建对话框(子组件自持表单状态, 保存成功后刷新列表) -->
    <ModelConfigFormDialog ref="formDialogRef" :is-admin="isAdmin" @saved="fetchData" />

    <!-- 模型测试对话框(单独测试 + 能力测试, 子组件自持状态) -->
    <ModelTestDialog ref="testDialogRef" @suggest-applied="handleSuggestApplied"
      @capability-updated="handleCapabilityUpdated" />
  </div>
</template>

<script setup lang="ts">
import { deleteModelConfig, listModelConfigs, revectorizeChunks, getRevectorizeStatus } from '../api/model_config'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import { useAuthStore } from '@/common/stores/auth'
import { useResponsive } from '@/common/composables/useResponsive'
import { usePermission } from '@/common/composables/usePermission'
import { formatTimeShort } from '@/common/utils/datetime'
import {
  ModelScope,
  modelTypeOptions,
  modelTypeTagType,
  serverTypeOptionsFor,
  modelTypeLabel,
  serverTypeLabel,
  modelScopeOptions,
  scopeShortLabel,
  modelMainLabel,
  testedCapabilities,
  type ModelConfig,
  type ModelCapabilityResult,
  type RerankScoreSuggest,
} from '../types/model_config'
import { ElMessage, ElMessageBox } from 'element-plus'
import ModelConfigFormDialog from '../components/ModelConfigFormDialog.vue'
import ModelTestDialog from '../components/ModelTestDialog.vue'

// ################ 当前用户与权限 ################
const authStore = useAuthStore()
const { isAdmin } = usePermission()

// 响应式: 平板及以上操作列固定右侧
const { isMd } = useResponsive()
const currentUserId = computed(() => authStore.authState.user.id)

/** 是否可管理(编辑/删除)该模型: 全局管理员或创建者本人 */
const canManage = (row: ModelConfig) => isAdmin.value || row.user_id === currentUserId.value

/** 不生效模型整行灰显样式 */
const inactiveRowClass = ({ row }: { row: ModelConfig }) => (row.is_active === false ? 'inactive-row' : '')

/** 归属范围标签样式 */
const scopeTagType: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
  [ModelScope.PUBLIC]: 'success',
  [ModelScope.DEPT]: 'warning',
  [ModelScope.USER]: 'info',
}

// ################ 搜索 ################
// 搜索字段配置(模型标识/类型/方案多字段筛选; 管理员可按所有者用户名过滤)
const searchFields = computed<SearchField[]>(() => {
  const fields: SearchField[] = [
    { prop: 'model', label: '模型标识' },
    {
      prop: 'model_type', label: '模型类型', type: 'select',
      options: modelTypeOptions.map(o => ({ label: o.label, value: o.value as string })),
    },
    {
      prop: 'server_type', label: '服务方案', type: 'select',
      options: [...serverTypeOptionsFor('chat'), ...serverTypeOptionsFor('asr')]
        .map(o => ({ label: o.label, value: o.value as string })),
    },
    {
      prop: 'scope', label: '归属范围', type: 'select',
      options: modelScopeOptions.map(o => ({ label: o.label, value: o.value as string })),
    },
  ]
  // 管理员: 按所有者用户名模糊过滤(查看所有人的模型)
  if (isAdmin.value) {
    fields.push({ prop: 'user', label: '所有者' })
  }
  return fields
})
// 查询参数(与后端列表接口过滤参数对齐)
const queryParams = ref<Record<string, unknown>>({
  model: '',
  model_type: undefined,
  server_type: undefined,
  scope: undefined,
  user: undefined,
})

// ################ 列表 ################
const pagination = ref<PaginationParams>({ page: 1, size: 10 })
const tableData = ref<ModelConfig[]>([])
const total = ref(0)
const loading = ref(false)

/** 获取数据(携带多字段过滤参数) */
const fetchData = async () => {
  try {
    loading.value = true
    const { model, model_type, server_type, scope, user } = queryParams.value
    const response: PaginationResponse<ModelConfig> = await listModelConfigs({
      ...pagination.value,
      model: (model as string) || undefined,
      model_type: (model_type as string) || undefined,
      server_type: (server_type as string) || undefined,
      scope: (scope as string) || undefined,
      user: (user as string) || undefined,
    } as PaginationParams)
    tableData.value = response.items
    total.value = response.total
  }
  catch (error) {
    console.error('获取模型配置列表失败:', error)
    ElMessage.error('获取数据失败，请重试')
  }
  finally {
    loading.value = false
  }
}

/** 搜索/重置: 回到第一页后重新查询 */
const handleSearch = () => {
  pagination.value.page = 1
  fetchData()
}

// 时间格式化: 统一使用 @/common/utils/datetime (formatTimeShort)

// ################ 全库重向量化(管理员) ################
const revectorizing = ref(false)
let revTimer: ReturnType<typeof setTimeout> | null = null

/** 轮询任务进度(每2秒, PROGRESS/提交中继续轮询) */
const pollRevectorizeStatus = (taskId: string) => {
  revTimer = setTimeout(async () => {
    try {
      const status = await getRevectorizeStatus(taskId)
      if (status.state === 'PROGRESS') {
        revectorizing.value = true
        // meta 偶发缺失时也要继续轮询, 避免进度链路卡死(按钮永远禁用)
        if (status.meta) {
          ElMessage.info(`重向量化进度: ${status.meta.processed}/${status.meta.total} 文档, 已处理 ${status.meta.chunks} 块`)
        }
        pollRevectorizeStatus(taskId)
      }
      else if (status.state === 'SUCCESS') {
        revectorizing.value = false
        ElMessage.success('全库重向量化完成')
      }
      else if (status.state === 'FAILURE') {
        revectorizing.value = false
        ElMessage.error(`重向量化失败: ${status.error ?? '未知错误'}`)
      }
      else {
        // PENDING/RETRY 等中间状态继续轮询
        pollRevectorizeStatus(taskId)
      }
    }
    catch (error) {
      console.error('查询重向量化进度失败:', error)
      revectorizing.value = false
    }
  }, 2000)
}

/** 提交全库重向量化任务(使用当前生效的默认公共向量化模型) */
const handleRevectorize = () => {
  ElMessageBox.confirm(
    '将以当前生效的默认向量化模型重新计算全部文档向量, 数据量大时耗时较长, 确定执行吗?',
    '重建向量索引',
    { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
  )
    .then(async () => {
      try {
        revectorizing.value = true
        const res = await revectorizeChunks()
        ElMessage.success(res.message || '任务已提交')
        pollRevectorizeStatus(res.task_id)
      }
      catch (error) {
        console.error('提交重向量化任务失败:', error)
        revectorizing.value = false
        ElMessage.error('任务提交失败')
      }
    })
    .catch(() => {})
}

onBeforeUnmount(() => {
  if (revTimer) clearTimeout(revTimer)
})

// ################ 对话框编排(表单/测试子组件) ################
const formDialogRef = ref<InstanceType<typeof ModelConfigFormDialog>>()
const testDialogRef = ref<InstanceType<typeof ModelTestDialog>>()

/** 打开创建对话框 */
const handleCreate = () => {
  formDialogRef.value?.open()
}

/** 打开编辑对话框(子组件拉取详情并回填) */
const handleEdit = (row: ModelConfig) => {
  formDialogRef.value?.open(row)
}

// ################ 能力测试 ################
/** 打开模型测试对话框(单独测试 + 能力测试; 无历史结果时对话框自动运行全部能力测试) */
const handleTest = (row: ModelConfig) => {
  const history = row.check_result ? Object.values(row.check_result) : []
  testDialogRef.value?.open(row, history)
}

/** 子组件能力测试完成: 合并结果到本地行数据(后端已同步持久化) */
const handleCapabilityUpdated = (payload: { modelId: string, capabilities: ModelCapabilityResult[] }) => {
  const idx = tableData.value.findIndex(r => r.id === payload.modelId)
  if (idx < 0) return
  const merged: Record<string, ModelCapabilityResult> = { ...(tableData.value[idx].check_result ?? {}) }
  for (const cap of payload.capabilities) merged[cap.capability] = { ...cap, checked_at: new Date().toISOString() }
  tableData.value[idx] = { ...tableData.value[idx], check_result: merged }
}

/** 子组件已应用 rerank 分数范围建议: 同步本地行数据(extra + 能力标签中的建议状态) */
const handleSuggestApplied = (payload: { modelId: string, suggest: RerankScoreSuggest, capabilities: ModelCapabilityResult[] }) => {
  const idx = tableData.value.findIndex(r => r.id === payload.modelId)
  if (idx < 0) return
  const mergedExtra = { ...(tableData.value[idx].extra ?? {}), score_min: payload.suggest.score_min, score_max: payload.suggest.score_max }
  const checkResult = { ...(tableData.value[idx].check_result ?? {}) }
  for (const cap of payload.capabilities) {
    if (cap.suggest) checkResult[cap.capability] = { ...checkResult[cap.capability], suggest: { ...cap.suggest, need_fix: false } }
  }
  tableData.value[idx] = { ...tableData.value[idx], extra: mergedExtra, check_result: checkResult }
}

// ################ 删除 ################
/** 删除模型配置 */
const handleDelete = (row: ModelConfig) => {
  ElMessageBox.confirm(
    `确定删除模型「${row.model}」的配置吗?`,
    '删除确认',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
    .then(async () => {
      try {
        await deleteModelConfig(row.id)
        ElMessage.success('删除成功')
        if (tableData.value.length === 1 && pagination.value.page > 1) {
          pagination.value.page -= 1
        }
        await fetchData()
      }
      catch (error) {
        console.error('删除模型配置失败:', error)
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
/* 不生效(灰色)模型行: 整行弱化显示 */
:deep(.el-table .inactive-row) {
  opacity: 0.55;
}
:deep(.el-table .inactive-row td) {
  color: var(--el-text-color-secondary);
}
</style>
