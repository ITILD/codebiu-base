<script lang="ts">
/**
 * ProTable 通用增强表格
 * - 列设置(显隐/顺序/重置) + 行密度切换, 按 tableKey 持久化到 localStorage
 * - 批量选择: 选中后显示批量操作条(selectable)
 * - 行内编辑: 编辑态单元格切换为控件, Enter 保存 / Esc 取消(editable)
 * - 响应式: <768 自动切换卡片列表; 平板(768-1023)取消固定列并收窄内边距
 * 用法示例:
 * <ProTable :columns="columns" :data="tableData" :loading="loading" table-key="main-audit" card-title-prop="path">
 *   <template #col-status="{ row }"><el-tag>{{ row.status }}</el-tag></template>
 *   <template #row-actions="{ row }"><el-button link @click="detail(row)">详情</el-button></template>
 * </ProTable>
 */
export type { ProTableColumn, ProTableDensity, ProTableRow } from './useProTablePrefs'
</script>

<template>
  <div class="pro-table w-full min-w-0">
    <!-- 工具栏: 左侧业务插槽(toolbar) + 右侧密度/列设置 -->
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <slot name="toolbar" />
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <!-- 行密度 -->
        <el-select
          :model-value="density"
          size="small"
          class="w-[104px]"
          :aria-label="t('pt_density')"
          @update:model-value="handleDensityChange"
        >
          <el-option :label="t('pt_density_default')" value="default" />
          <el-option :label="t('pt_density_medium')" value="medium" />
          <el-option :label="t('pt_density_small')" value="small" />
        </el-select>

        <!-- 列设置 -->
        <el-popover
          v-model:visible="colPanelVisible"
          placement="bottom-end"
          :width="272"
          trigger="click"
        >
          <template #reference>
            <el-button
              size="small"
              :icon="Operation"
              :aria-label="t('pt_col_settings')"
              :title="t('pt_col_settings')"
            >
              <span class="hidden md:inline">{{ t('pt_col_settings') }}</span>
            </el-button>
          </template>

          <p class="mb-2 text-xs text-note-sub">{{ t('pt_col_hint') }}</p>
          <ul class="max-h-[46vh] overflow-y-auto">
            <li v-for="col in orderedColumns" :key="col.prop" class="flex items-center gap-1">
              <el-checkbox
                :model-value="!isColumnHidden(col.prop)"
                @change="toggleColumn(col.prop)"
              >
                <span v-ellipsis class="max-w-[168px] text-sm text-note">{{ col.label }}</span>
              </el-checkbox>
              <span class="ml-auto flex items-center">
                <el-button
                  link
                  size="small"
                  :icon="ArrowUp"
                  :disabled="!canMoveUp(col.prop)"
                  :aria-label="`${t('pt_move_up')} ${col.label}`"
                  @click="moveColumn(col.prop, -1)"
                />
                <el-button
                  link
                  size="small"
                  :icon="ArrowDown"
                  :disabled="!canMoveDown(col.prop)"
                  :aria-label="`${t('pt_move_down')} ${col.label}`"
                  @click="moveColumn(col.prop, 1)"
                />
              </span>
            </li>
          </ul>
          <div class="mt-2 flex justify-end">
            <el-button link type="primary" size="small" :aria-label="t('pt_reset')" @click="reset">
              {{ t('pt_reset') }}
            </el-button>
          </div>
        </el-popover>
      </div>
    </div>

    <!-- 批量选择条 -->
    <div
      v-if="selectable && selectedRows.length"
      class="mb-2 flex flex-wrap items-center gap-2 rounded-note-md bg-note-tint px-3 py-2"
    >
      <span class="text-sm text-note-green">{{ t('pt_selected', { n: selectedRows.length }) }}</span>
      <div class="flex flex-wrap items-center gap-2">
        <slot name="batch-actions" :rows="selectedRows" />
      </div>
      <el-button
        class="ml-auto"
        link
        size="small"
        :aria-label="t('pt_clear_selection')"
        @click="clearSelection"
      >
        {{ t('pt_clear_selection') }}
      </el-button>
    </div>

    <!-- 手机(<768): 卡片列表 -->
    <div v-if="!isMd" class="flex w-full min-w-0 flex-col gap-3">
      <template v-if="loading">
        <NoteSkeleton v-for="i in skeletonRows" :key="i" variant="post" />
      </template>
      <el-empty v-else-if="data.length === 0" :description="t('pt_empty')" :image-size="72" />
      <template v-else>
        <article
          v-for="(row, index) in data"
          :key="rowKeyOf(row, index)"
          class="rounded-note-md bg-note-card p-3 shadow-note"
        >
          <slot name="mobile-card" :row="row" :columns="mobileColumns" :editing="isEditing(row)">
            <!-- 卡片标题 + 操作区 -->
            <div class="flex items-start justify-between gap-2">
              <h4 v-ellipsis class="min-w-0 flex-1 truncate text-sm font-bold text-note">{{ mobileTitle(row) }}</h4>
              <div class="flex shrink-0 items-center gap-1">
                <template v-if="isEditing(row)">
                  <el-button link type="primary" size="small" :aria-label="t('pt_save')" @click="saveEdit">
                    {{ t('pt_save') }}
                  </el-button>
                  <el-button link size="small" :aria-label="t('pt_cancel')" @click="cancelEdit">
                    {{ t('pt_cancel') }}
                  </el-button>
                </template>
                <template v-else>
                  <el-button
                    v-if="editable"
                    link
                    type="primary"
                    size="small"
                    :aria-label="t('pt_edit')"
                    @click="startEdit(row)"
                  >
                    {{ t('pt_edit') }}
                  </el-button>
                  <slot name="row-actions" :row="row" />
                </template>
              </div>
            </div>

            <!-- 编辑态: 仅编辑列 -->
            <div v-if="isEditing(row)" class="mt-2 flex flex-col gap-2">
              <label v-for="col in editableColumns" :key="col.prop" class="flex items-center gap-2">
                <span class="w-16 shrink-0 text-xs text-note-sub">{{ col.label }}</span>
                <el-input
                  v-if="editorOf(col) === 'input'"
                  v-model="draft[col.prop]"
                  size="small"
                  class="flex-1"
                  :aria-label="col.label"
                  @keyup.enter="saveEdit"
                  @keyup.esc="cancelEdit"
                />
                <el-input-number
                  v-else-if="editorOf(col) === 'number'"
                  v-model="draft[col.prop]"
                  size="small"
                  controls-position="right"
                  class="flex-1"
                  :aria-label="col.label"
                  @keyup.enter="saveEdit"
                  @keyup.esc="cancelEdit"
                />
                <el-select
                  v-else-if="editorOf(col) === 'select'"
                  v-model="draft[col.prop]"
                  size="small"
                  class="flex-1"
                  :aria-label="col.label"
                  @keyup.esc="cancelEdit"
                >
                  <el-option
                    v-for="opt in col.options ?? []"
                    :key="String(opt.value)"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <el-switch
                  v-else-if="editorOf(col) === 'switch'"
                  v-model="draft[col.prop]"
                  :aria-label="col.label"
                />
                <el-date-picker
                  v-else-if="editorOf(col) === 'date'"
                  v-model="draft[col.prop]"
                  type="date"
                  size="small"
                  class="flex-1"
                  :aria-label="col.label"
                  @keyup.esc="cancelEdit"
                />
                <span v-else class="min-w-0 flex-1 text-xs text-note">{{ displayValue(col, row, index) }}</span>
              </label>
            </div>

            <!-- 阅读态: 前 3 个可见列 -->
            <dl v-else class="mt-2 grid grid-cols-1 gap-1.5 text-xs">
              <div v-for="col in mobileColumns" :key="col.prop" class="flex items-start gap-2">
                <dt class="w-16 shrink-0 text-note-sub">{{ col.label }}</dt>
                <!-- 卡片值统一两行省略: 保持卡片高度一致, 长文本 hover(桌面)显示全文 -->
                <dd v-ellipsis:2 class="min-w-0 flex-1 text-note">{{ displayValue(col, row, index) }}</dd>
              </div>
            </dl>
          </slot>
        </article>
      </template>
    </div>

    <!-- 平板/桌面表格 -->
    <div v-else class="w-full min-w-0" :class="tableClass">
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="data"
        :size="tableSize"
        :row-key="rowKey"
        stripe
        class="w-full"
        @selection-change="handleSelectionChange"
      >
        <el-table-column
          v-if="selectable"
          type="selection"
          width="44"
          :fixed="isLg ? 'left' : false"
        />
        <el-table-column
          v-for="col in visibleColumns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth ?? 100"
          :align="col.align ?? 'left'"
          :fixed="columnFixed(col)"
          :sortable="col.sortable ?? false"
          :show-overflow-tooltip="col.showOverLimit !== false"
        >
          <template #default="{ row, $index }">
            <!-- 编辑态: 控件 -->
            <template v-if="isCellEditing(col, row)">
              <el-input
                v-if="editorOf(col) === 'input'"
                v-model="draft[col.prop]"
                size="small"
                :aria-label="col.label"
                @keyup.enter="saveEdit"
                @keyup.esc="cancelEdit"
              />
              <el-input-number
                v-else-if="editorOf(col) === 'number'"
                v-model="draft[col.prop]"
                size="small"
                controls-position="right"
                class="w-full"
                :aria-label="col.label"
                @keyup.enter="saveEdit"
                @keyup.esc="cancelEdit"
              />
              <el-select
                v-else-if="editorOf(col) === 'select'"
                v-model="draft[col.prop]"
                size="small"
                class="w-full"
                :aria-label="col.label"
                @keyup.esc="cancelEdit"
              >
                <el-option
                  v-for="opt in col.options ?? []"
                  :key="String(opt.value)"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-switch
                v-else-if="editorOf(col) === 'switch'"
                v-model="draft[col.prop]"
                :aria-label="col.label"
              />
              <el-date-picker
                v-else-if="editorOf(col) === 'date'"
                v-model="draft[col.prop]"
                type="date"
                size="small"
                class="w-full"
                :aria-label="col.label"
                @keyup.esc="cancelEdit"
              />
              <template v-else>{{ displayValue(col, row, $index) }}</template>
            </template>

            <!-- 动态列插槽: col-<prop> -->
            <slot
              v-else-if="hasColumnSlot(col)"
              :name="columnSlotName(col)"
              :row="row"
              :value="row[col.prop]"
              :index="$index"
            >
              {{ displayValue(col, row, $index) }}
            </slot>
            <template v-else>{{ displayValue(col, row, $index) }}</template>
          </template>
        </el-table-column>

        <!-- 操作列: 编辑/保存/取消 + row-actions 插槽 -->
        <el-table-column
          v-if="hasActions"
          :label="t('pt_actions')"
          min-width="120"
          align="center"
          :fixed="isLg ? 'right' : false"
        >
          <template #default="{ row }">
            <template v-if="isEditing(row)">
              <el-button link type="primary" size="small" :aria-label="t('pt_save')" @click="saveEdit">
                {{ t('pt_save') }}
              </el-button>
              <el-button link size="small" :aria-label="t('pt_cancel')" @click="cancelEdit">
                {{ t('pt_cancel') }}
              </el-button>
            </template>
            <template v-else>
              <el-button
                v-if="editable"
                link
                type="primary"
                size="small"
                :aria-label="t('pt_edit')"
                @click="startEdit(row)"
              >
                {{ t('pt_edit') }}
              </el-button>
              <slot name="row-actions" :row="row" />
            </template>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty :description="t('pt_empty')" :image-size="72" />
        </template>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowDown, ArrowUp, Operation } from '@element-plus/icons-vue'
import type { TableInstance } from 'element-plus'
import NoteSkeleton from '@/common/components/NoteSkeleton.vue'
import { i18n } from '@/common/i18n/language'
import { useResponsive } from '@/common/composables/useResponsive'
import {
  useProTablePrefs,
  type ProTableColumn,
  type ProTableRow,
} from './useProTablePrefs'

interface Props {
  /** 列配置(渲染顺序/显隐由列设置接管) */
  columns: ProTableColumn[]
  /** 表格数据 */
  data: ProTableRow[]
  /** 列设置/密度持久化标识(建议 `<模块>-<页面>`) */
  tableKey: string
  /** 加载中(表格 v-loading / 卡片骨架) */
  loading?: boolean
  /** 开启批量选择列与批量操作条 */
  selectable?: boolean
  /** 开启行内编辑 */
  editable?: boolean
  /** el-table 行唯一键字段 */
  rowKey?: string
  /** 手机卡片标题字段(缺省取第一个可见列) */
  cardTitleProp?: string
  /** 手机卡片骨架条数 */
  skeletonRows?: number
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  selectable: false,
  editable: false,
  rowKey: 'id',
  cardTitleProp: '',
  skeletonRows: 3,
})

const emit = defineEmits<{
  /** 行内编辑保存: changed 仅包含被修改的编辑列 */
  (e: 'save', payload: { row: ProTableRow; changed: Record<string, any> }): void
  /** 多选变化 */
  (e: 'selection-change', rows: ProTableRow[]): void
}>()

const { t } = i18n.global
// 断点: <768 卡片视图, 768-1023 平板(取消固定列), >=1024 桌面
const { isMd, isLg } = useResponsive()
const slots = useSlots()

const {
  density,
  orderedColumns,
  visibleColumns,
  isColumnHidden,
  toggleColumn,
  canMoveUp,
  canMoveDown,
  moveColumn,
  setDensity,
  reset,
} = useProTablePrefs(
  computed(() => props.columns),
  props.tableKey,
)

const tableRef = ref<TableInstance>()
const colPanelVisible = ref(false)
const selectedRows = ref<ProTableRow[]>([])

// 行内编辑: 直接以行对象引用作为编辑标识(同一数据源对象稳定)
const editingRow = ref<ProTableRow | null>(null)
const draft = ref<ProTableRow>({})
const original = ref<ProTableRow>({})

/** 密度 → el-table size(紧凑在 small 基础上再压缩内边距) */
const tableSize = computed<'default' | 'small'>(() =>
  density.value === 'default' ? 'default' : 'small',
)

/** 平板收窄内边距 / 紧凑密度附加样式 */
const tableClass = computed(() => ({
  'pro-table--tablet': isMd.value && !isLg.value,
  'pro-table--density-compact': density.value === 'small',
}))

/** 手机卡片展示的前 3 个可见列 */
const mobileColumns = computed(() => visibleColumns.value.slice(0, 3))

/** 参与行内编辑的可见列 */
const editableColumns = computed(() => visibleColumns.value.filter((col) => col.editable))

/** 是否需要操作列(可编辑或页面提供了 row-actions 插槽) */
const hasActions = computed(() => props.editable || !!slots['row-actions'])

/** 密度切换(仅接受合法枚举值) */
const handleDensityChange = (value: string) => {
  if (value === 'default' || value === 'medium' || value === 'small') setDensity(value)
}

/** 平板及以下取消固定列, 避免遮挡内容 */
const columnFixed = (col: ProTableColumn) => (isLg.value ? (col.fixed ?? false) : false)

/** 编辑器类型(缺省 input) */
const editorOf = (col: ProTableColumn) => col.editor ?? 'input'

/** 动态列插槽名 */
const columnSlotName = (col: ProTableColumn) => `col-${col.prop}`

/** 列插槽是否可用(声明 slot 或页面实际提供了同名插槽) */
const hasColumnSlot = (col: ProTableColumn) =>
  !!(col.slot || slots[columnSlotName(col)])

/** 展示文本: formatter 优先, 空值统一为 — */
const displayValue = (col: ProTableColumn, row: ProTableRow, index: number): string => {
  const raw = row[col.prop]
  const text = col.formatter ? col.formatter(row, raw, index) : raw
  return text === null || text === undefined || text === '' ? '—' : String(text)
}

/** 卡片标题(缺省取第一个可见列的值) */
const mobileTitle = (row: ProTableRow): string => {
  const prop = props.cardTitleProp || mobileColumns.value[0]?.prop
  if (!prop) return '—'
  const value = row[prop]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

/** 卡片列表 key: 优先行主键, 缺失时退回下标 */
const rowKeyOf = (row: ProTableRow, index: number): string | number => {
  const key = row[props.rowKey]
  return typeof key === 'string' || typeof key === 'number' ? key : index
}

/** 进入编辑态(浅拷贝行数据, 取消时原行不受影响) */
const startEdit = (row: ProTableRow) => {
  editingRow.value = row
  draft.value = { ...row }
  original.value = { ...row }
}

const isEditing = (row: ProTableRow) => editingRow.value === row

const isCellEditing = (col: ProTableColumn, row: ProTableRow) =>
  isEditing(row) && !!col.editable

/** 保存: 计算编辑列差异后 emit, 由页面决定是否刷新数据 */
const saveEdit = () => {
  if (!editingRow.value) return
  const changed: Record<string, any> = {}
  for (const col of editableColumns.value) {
    if (!Object.is(draft.value[col.prop], original.value[col.prop])) {
      changed[col.prop] = draft.value[col.prop]
    }
  }
  emit('save', { row: { ...draft.value }, changed })
  editingRow.value = null
}

/** 取消编辑: 丢弃草稿 */
const cancelEdit = () => {
  editingRow.value = null
}

const handleSelectionChange = (rows: ProTableRow[]) => {
  selectedRows.value = rows
  emit('selection-change', rows)
}

/** 清空多选(批量操作条"取消选择") */
const clearSelection = () => {
  tableRef.value?.clearSelection()
  selectedRows.value = []
}

defineExpose({
  clearSelection,
  getSelection: () => selectedRows.value,
})
</script>

<style scoped>
/* 平板(768-1023): 取消固定列后收窄单元格内边距, 降低横向拥挤 */
.pro-table--tablet :deep(.el-table .cell) {
  padding-left: 8px;
  padding-right: 8px;
}

/* 紧凑密度: 在 el-table small 基础上再压行高与字号 */
.pro-table--density-compact :deep(.el-table .el-table__cell) {
  padding-top: 2px;
  padding-bottom: 2px;
}

.pro-table--density-compact :deep(.el-table .cell) {
  font-size: 12px;
  line-height: 18px;
}
</style>
