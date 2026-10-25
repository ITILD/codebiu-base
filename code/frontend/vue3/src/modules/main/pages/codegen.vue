<template>
  <div p-4 md:p-6 w-full min-w-0 class="codegen-page">
    <!-- 水墨页头 -->
    <InkPageHead :title="t('cg_title')" seal="码">
      <template #sub>{{ t('cg_subtitle') }}</template>
    </InkPageHead>

    <div class="flex flex-col items-start gap-4 lg:flex-row">
      <!-- ############ 桌面: 左侧数据表列表 ############ -->
      <aside v-if="isLg" class="page-card w-64 shrink-0 lg:sticky lg:top-4">
        <h3 class="mb-2 font-bold text-note">{{ t('cg_pick_table') }}</h3>
        <div class="flex flex-col gap-2">
          <el-input
            v-model="tableKeyword"
            :placeholder="t('cg_search_table')"
            :prefix-icon="Search"
            clearable
            :aria-label="t('cg_search_table')"
            @clear="fetchTables"
            @keyup.enter="fetchTables"
          />
          <div
            v-loading="tableLoading"
            class="flex max-h-[calc(100vh-20rem)] flex-col gap-1 overflow-y-auto"
          >
            <button
              v-for="tb in tables"
              :key="tb.name"
              type="button"
              class="note-transition w-full cursor-pointer rounded-note-sm border-none px-2.5 py-2 text-left"
              :class="selectedTable?.name === tb.name
                ? 'bg-note-green/10 text-note-green'
                : 'bg-transparent text-note hover:bg-note-tint'"
              :aria-pressed="selectedTable?.name === tb.name"
              :aria-label="`${t('cg_pick_table')}: ${tb.name}`"
              @click="handleSelectTable(tb)"
            >
              <span v-ellipsis class="block truncate font-mono text-sm font-medium">{{ tb.name }}</span>
              <span v-ellipsis class="block truncate text-xs text-note-sub">
                {{ tb.comment || '—' }} · {{ tb.column_count }}
              </span>
            </button>
            <p v-if="!tableLoading && !tables.length" class="py-4 text-center text-xs text-note-sub">
              {{ t('cg_no_table') }}
            </p>
          </div>
        </div>
      </aside>

      <div class="flex w-full min-w-0 flex-1 flex-col gap-4">
        <!-- ############ 平板/手机: 已选数据表 + 抽屉入口 ############ -->
        <div v-if="!isLg" class="page-card flex flex-wrap items-center gap-3">
          <div class="min-w-0 flex-1">
            <p class="text-xs text-note-sub">{{ t('cg_selected_table') }}</p>
            <p v-ellipsis class="truncate text-sm font-medium text-note">
              {{ selectedTable ? selectedTable.name : t('cg_need_table') }}
            </p>
            <p v-if="selectedTable?.comment" v-ellipsis class="truncate text-xs text-note-sub">
              {{ selectedTable.comment }}
            </p>
          </div>
          <el-button :icon="Search" @click="pickerVisible = true">
            {{ t('cg_pick_table') }}
          </el-button>
        </div>

        <!-- ############ 未选表空状态 ############ -->
        <div v-if="!selectedTable" page-card>
          <el-empty :description="t('cg_need_table')" :image-size="72" />
        </div>

        <!-- ############ 配置区 ############ -->
        <div v-else v-loading="tableDetailLoading" class="flex flex-col gap-4">
          <!-- 基础信息 -->
          <div class="page-card">
            <div class="card-toolbar">
              <h3 class="font-bold text-note">{{ t('cg_basic') }}</h3>
              <el-tag size="small" type="info">{{ selectedTable.name }}</el-tag>
            </div>

            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p class="mb-1 text-xs text-note-sub">{{ t('cg_module_name') }}</p>
                <el-input v-model="moduleName" :aria-label="t('cg_module_name')" />
              </div>
              <div>
                <p class="mb-1 text-xs text-note-sub">{{ t('cg_class_name') }}</p>
                <el-input v-model="className" :aria-label="t('cg_class_name')" />
              </div>
              <div>
                <p class="mb-1 text-xs text-note-sub">{{ t('cg_page_title') }}</p>
                <el-input v-model="pageTitle" :aria-label="t('cg_page_title')" />
              </div>
            </div>

            <div class="mt-4 flex flex-wrap items-start gap-x-8 gap-y-3">
              <!-- AI 辅助开关 -->
              <div class="flex min-w-0 items-start gap-2.5">
                <el-switch v-model="useAi" :aria-label="t('cg_use_ai')" />
                <div class="min-w-0">
                  <p class="text-sm leading-tight text-note">{{ t('cg_use_ai') }}</p>
                  <p class="text-xs leading-tight text-note-sub">{{ t('cg_use_ai_desc') }}</p>
                </div>
              </div>

              <!-- 生成内容 -->
              <div class="flex flex-col gap-1">
                <p class="text-xs text-note-sub">{{ t('cg_templates') }}</p>
                <div class="flex flex-wrap gap-x-4 gap-y-1">
                  <el-checkbox v-model="includeBackend">{{ t('cg_tpl_backend') }}</el-checkbox>
                  <el-checkbox v-model="includeFrontend">{{ t('cg_tpl_frontend') }}</el-checkbox>
                </div>
              </div>
            </div>
          </div>

          <!-- 字段配置 -->
          <div class="page-card">
            <div class="card-toolbar">
              <h3 class="flex items-center gap-2 font-bold text-note">
                {{ t('cg_columns') }}
                <el-tag size="small">{{ columns.length }}</el-tag>
              </h3>

              <!-- 操作按钮组: 手机纵向铺满, 桌面右对齐 -->
              <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                <el-button
                  :icon="MagicStick"
                  :loading="suggestLoading"
                  :disabled="!selectedTable"
                  @click="handleSuggest"
                >
                  {{ t('cg_suggest') }}
                </el-button>
                <el-button
                  :icon="View"
                  :loading="previewLoading"
                  :disabled="!selectedTable || (!includeBackend && !includeFrontend)"
                  @click="handlePreview"
                >
                  {{ t('cg_preview') }}
                </el-button>
                <el-button
                  type="primary"
                  :icon="Download"
                  :loading="generateLoading"
                  :disabled="!selectedTable || (!includeBackend && !includeFrontend)"
                  @click="handleGenerate"
                >
                  {{ t('cg_generate') }}
                </el-button>
              </div>
            </div>

            <!-- 桌面: 字段配置表 -->
            <el-table v-if="isLg && columns.length" :data="columns" size="small" stripe max-height="480">
              <el-table-column :label="t('cg_col_name')" min-width="150">
                <template #default="{ row }">
                  <div class="min-w-0">
                    <span v-ellipsis class="block truncate font-mono text-xs">{{ row.name }}</span>
                    <span v-ellipsis class="block truncate text-[11px] text-note-sub">{{ sqlTypeText(row.name) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_label')" min-width="130">
                <template #default="{ row }">
                  <el-input
                    v-model="row.label"
                    size="small"
                    :aria-label="`${row.name} ${t('cg_col_label')}`"
                  />
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_control')" width="118">
                <template #default="{ row }">
                  <el-select
                    v-model="row.control"
                    size="small"
                    :aria-label="`${row.name} ${t('cg_col_control')}`"
                  >
                    <el-option
                      v-for="opt in controlOptions"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_required')" width="62" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.required" size="small" :aria-label="`${row.name} ${t('cg_col_required')}`" />
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_searchable')" width="62" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.searchable" size="small" :aria-label="`${row.name} ${t('cg_col_searchable')}`" />
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_listable')" width="62" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.listable" size="small" :aria-label="`${row.name} ${t('cg_col_listable')}`" />
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_editable')" width="62" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.editable" size="small" :aria-label="`${row.name} ${t('cg_col_editable')}`" />
                </template>
              </el-table-column>
              <el-table-column :label="t('cg_col_width')" width="96">
                <template #default="{ row }">
                  <el-input-number
                    v-model="row.width"
                    size="small"
                    :min="60"
                    :max="600"
                    :step="10"
                    controls-position="right"
                    class="!w-full"
                    :aria-label="`${row.name} ${t('cg_col_width')}`"
                  />
                </template>
              </el-table-column>
            </el-table>

            <!-- 平板/手机: 字段卡片折叠 -->
            <el-collapse v-else-if="columns.length" class="codegen-field-cards">
              <el-collapse-item v-for="row in columns" :key="row.name" :name="row.name">
                <template #title>
                  <div class="flex min-w-0 items-center gap-2">
                    <span v-ellipsis class="truncate font-mono text-xs">{{ row.name }}</span>
                    <span v-ellipsis class="truncate text-xs text-note-sub">{{ row.label }}</span>
                  </div>
                </template>
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <p class="mb-1 text-xs text-note-sub">{{ t('cg_col_label') }}</p>
                    <el-input v-model="row.label" size="small" :aria-label="`${row.name} ${t('cg_col_label')}`" />
                  </div>
                  <div>
                    <p class="mb-1 text-xs text-note-sub">{{ t('cg_col_control') }}</p>
                    <el-select
                      v-model="row.control"
                      size="small"
                      class="!w-full"
                      :aria-label="`${row.name} ${t('cg_col_control')}`"
                    >
                      <el-option
                        v-for="opt in controlOptions"
                        :key="opt.value"
                        :label="opt.label"
                        :value="opt.value"
                      />
                    </el-select>
                  </div>
                  <div class="flex flex-wrap gap-x-4 gap-y-2 sm:col-span-2">
                    <span class="flex items-center gap-1.5 text-xs text-note-sub">
                      <el-switch v-model="row.required" size="small" />{{ t('cg_col_required') }}
                    </span>
                    <span class="flex items-center gap-1.5 text-xs text-note-sub">
                      <el-switch v-model="row.searchable" size="small" />{{ t('cg_col_searchable') }}
                    </span>
                    <span class="flex items-center gap-1.5 text-xs text-note-sub">
                      <el-switch v-model="row.listable" size="small" />{{ t('cg_col_listable') }}
                    </span>
                    <span class="flex items-center gap-1.5 text-xs text-note-sub">
                      <el-switch v-model="row.editable" size="small" />{{ t('cg_col_editable') }}
                    </span>
                  </div>
                  <div class="sm:col-span-2">
                    <p class="mb-1 text-xs text-note-sub">{{ t('cg_col_width') }}</p>
                    <el-input-number
                      v-model="row.width"
                      size="small"
                      :min="60"
                      :max="600"
                      :step="10"
                      controls-position="right"
                      class="!w-full"
                      :aria-label="`${row.name} ${t('cg_col_width')}`"
                    />
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>

            <el-empty v-else :description="t('admin_no_data')" :image-size="64" />
          </div>

          <!-- 提示信息(智能建议/生成的 warnings) -->
          <div v-if="warnings.length" page-card>
            <h3 class="mb-2 font-bold text-note">{{ t('cg_warnings') }}</h3>
            <ul class="m-0 list-disc space-y-1 break-words pl-5 text-xs text-note-sub">
              <li v-for="(warn, index) in warnings" :key="index">{{ warn }}</li>
            </ul>
          </div>

          <!-- 生成结果 -->
          <div v-if="lastResult" page-card>
            <h3 class="mb-2 font-bold text-note">{{ t('cg_result') }}</h3>
            <div class="flex flex-wrap gap-2">
              <el-tag type="success" size="small">
                {{ t('cg_written', { n: lastResult.written.length }) }}
              </el-tag>
              <el-tag v-if="lastResult.skipped.length" type="info" size="small">
                {{ t('cg_skipped', { n: lastResult.skipped.length }) }}
              </el-tag>
            </div>

            <ul
              v-if="lastResult.written.length"
              class="m-0 mt-2 list-none space-y-1 break-all font-mono text-xs text-note-sub"
            >
              <li v-for="path in lastResult.written" :key="path">{{ path }}</li>
            </ul>
            <div v-if="lastResult.skipped.length" class="mt-2">
              <p class="mb-1 text-xs text-note-sub">
                {{ t('cg_skipped', { n: lastResult.skipped.length }) }}
              </p>
              <ul class="m-0 list-none space-y-1 break-all font-mono text-xs text-note-sub">
                <li v-for="path in lastResult.skipped" :key="path">{{ path }}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ############ 数据表选择抽屉(平板/手机) ############ -->
    <el-drawer v-model="pickerVisible" :title="t('cg_pick_table')" direction="btt" size="82%">
      <div class="flex flex-col gap-2">
        <el-input
          v-model="tableKeyword"
          :placeholder="t('cg_search_table')"
          :prefix-icon="Search"
          clearable
          :aria-label="t('cg_search_table')"
          @clear="fetchTables"
          @keyup.enter="fetchTables"
        />
        <div v-loading="tableLoading" class="flex max-h-[60vh] flex-col gap-1 overflow-y-auto">
          <button
            v-for="tb in tables"
            :key="tb.name"
            type="button"
            class="note-transition w-full cursor-pointer rounded-note-sm border-none px-2.5 py-2 text-left"
            :class="selectedTable?.name === tb.name
              ? 'bg-note-green/10 text-note-green'
              : 'bg-transparent text-note hover:bg-note-tint'"
            :aria-pressed="selectedTable?.name === tb.name"
            :aria-label="`${t('cg_pick_table')}: ${tb.name}`"
            @click="handleSelectTable(tb)"
          >
            <span v-ellipsis class="block truncate font-mono text-sm font-medium">{{ tb.name }}</span>
            <span v-ellipsis class="block truncate text-xs text-note-sub">
              {{ tb.comment || '—' }} · {{ tb.column_count }}
            </span>
          </button>
          <p v-if="!tableLoading && !tables.length" class="py-4 text-center text-xs text-note-sub">
            {{ t('cg_no_table') }}
          </p>
        </div>
      </div>
    </el-drawer>

    <!-- ############ 预览对话框(手机全屏) ############ -->
    <el-dialog
      v-model="previewVisible"
      :title="t('cg_preview')"
      :fullscreen="!isLg"
      width="94%"
      class="max-w-[1100px]"
      destroy-on-close
    >
      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <el-switch v-model="overwrite" :active-text="t('cg_overwrite')" />
          <span v-ellipsis class="truncate font-mono text-[11px] text-note-sub">
            {{ activePreview?.path }}
          </span>
        </div>

        <!-- 预览提示 -->
        <el-alert
          v-if="previewWarnings.length"
          type="warning"
          :closable="false"
          :title="t('cg_warnings')"
        >
          <ul class="m-0 list-disc space-y-1 pl-4 text-xs">
            <li v-for="(warn, index) in previewWarnings" :key="index">{{ warn }}</li>
          </ul>
        </el-alert>

        <div class="flex min-h-0 flex-col gap-3 lg:flex-row">
          <!-- 桌面: 左侧文件列表 -->
          <div v-if="isLg" class="flex max-h-[60vh] w-64 shrink-0 flex-col gap-1 overflow-y-auto">
            <button
              v-for="file in previewFiles"
              :key="file.path"
              type="button"
              class="note-transition flex w-full cursor-pointer items-center justify-between gap-2 rounded-note-sm border-none px-2 py-1.5 text-left"
              :class="file.path === activePreviewPath
                ? 'bg-note-green/10 text-note-green'
                : 'bg-note-soft text-note hover:bg-note-tint'"
              :aria-pressed="file.path === activePreviewPath"
              :aria-label="`${t('cg_preview')}: ${file.path}`"
              @click="activePreviewPath = file.path"
            >
              <span v-ellipsis class="truncate font-mono text-[11px]">{{ file.path }}</span>
              <el-tag v-if="file.exists" size="small" type="warning">{{ t('cg_exists') }}</el-tag>
            </button>
          </div>

          <!-- 平板/手机: 文件下拉 -->
          <el-select
            v-else
            v-model="activePreviewPath"
            class="!w-full"
            :aria-label="t('cg_preview')"
          >
            <el-option
              v-for="file in previewFiles"
              :key="file.path"
              :label="file.exists ? `${file.path} (${t('cg_exists')})` : file.path"
              :value="file.path"
            />
          </el-select>

          <!-- 代码块: 等宽字体 + 内部滚动, 不撑破页面 -->
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex justify-end">
              <el-button size="small" :icon="CopyDocument" @click="handleCopy">
                {{ copied ? t('cg_copied') : t('cg_copy') }}
              </el-button>
            </div>
            <pre
              class="m-0 max-h-[60vh] overflow-auto rounded-note-md bg-note-soft p-3 text-xs leading-relaxed text-note"
            ><code class="font-mono">{{ activePreview?.content }}</code></pre>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="previewVisible = false">{{ t('pt_cancel') }}</el-button>
        <el-button type="primary" :loading="generateLoading" @click="handleGenerate">
          {{ t('cg_generate') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * 代码生成器
 * 左侧选表 → 读取表结构 → AI/模板建议字段配置 → 预览文件 → 落盘生成
 * 桌面双栏, 平板/手机抽屉选表 + 字段卡片折叠
 */
import { ElMessage } from 'element-plus'
import { CopyDocument, Download, MagicStick, Search, View } from '@element-plus/icons-vue'
import { i18n } from '@/common/i18n/language'
import { useResponsive } from '@/common/composables/useResponsive'
import { copyToClipboard } from '@/common/utils/export'
import {
  generateCodegen,
  getCodegenTable,
  listCodegenTables,
  previewCodegen,
  suggestCodegen,
} from '../api/codegen'
import type {
  CodegenControl,
  CodegenFieldConfig,
  CodegenGenerateResult,
  CodegenPreviewFile,
  CodegenPreviewRequest,
  CodegenSuggestColumn,
  CodegenTable,
  CodegenTableColumn,
} from '../types/codegen'

const { t } = i18n.global
const { isLg } = useResponsive()

/** 控件枚举(用于后端字符串归一) */
const CONTROL_VALUES: CodegenControl[] = [
  'input',
  'textarea',
  'number',
  'switch',
  'select',
  'date',
  'datetime',
]

/** 控件下拉选项(文案随语言切换) */
const controlOptions = computed<{ label: string; value: CodegenControl }[]>(() => [
  { label: t('cg_control_input'), value: 'input' },
  { label: t('cg_control_textarea'), value: 'textarea' },
  { label: t('cg_control_number'), value: 'number' },
  { label: t('cg_control_switch'), value: 'switch' },
  { label: t('cg_control_select'), value: 'select' },
  { label: t('cg_control_date'), value: 'date' },
  { label: t('cg_control_datetime'), value: 'datetime' },
])

// ################ 数据表列表 ################
const tableKeyword = ref('')
const tableLoading = ref(false)
const tables = ref<CodegenTable[]>([])
const pickerVisible = ref(false)
const tableDetailLoading = ref(false)
const selectedTable = ref<CodegenTable | null>(null)
/** 字段元数据缓存: 字段名 → 原始类型信息(表格类型小字用) */
const columnMeta = ref<Record<string, CodegenTableColumn>>({})

// ################ 配置 ################
const moduleName = ref('')
const className = ref('')
const pageTitle = ref('')
const useAi = ref(true)
const includeBackend = ref(true)
const includeFrontend = ref(true)
const columns = ref<CodegenFieldConfig[]>([])
const warnings = ref<string[]>([])
const lastResult = ref<CodegenGenerateResult | null>(null)

// ################ 操作状态 ################
const suggestLoading = ref(false)
const previewLoading = ref(false)
const generateLoading = ref(false)

// ################ 预览 ################
const previewVisible = ref(false)
const previewFiles = ref<CodegenPreviewFile[]>([])
const previewWarnings = ref<string[]>([])
const activePreviewPath = ref('')
const overwrite = ref(false)
const copied = ref(false)

const activePreview = computed(() => {
  const files = previewFiles.value
  return files.find((file) => file.path === activePreviewPath.value) ?? files[0] ?? null
})

let keywordTimer: ReturnType<typeof setTimeout> | undefined
let copyTimer: ReturnType<typeof setTimeout> | undefined

/** 统一错误文案: 优先后端返回信息 */
function errorText(error: unknown): string {
  return error instanceof Error && error.message ? error.message : t('cg_error')
}

/** 拉取数据表列表(关键字支持表名/注释) */
async function fetchTables() {
  try {
    tableLoading.value = true
    const res = await listCodegenTables(tableKeyword.value.trim() || undefined)
    tables.value = res.items ?? []
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    tableLoading.value = false
  }
}

/** 表名转大驼峰(默认类名) */
function toPascalCase(name: string): string {
  return name
    .split(/[^a-zA-Z0-9]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')
}

/** 后端控件字符串 → 前端枚举(未知值回退 input) */
function normalizeControl(control?: string | null): CodegenControl {
  return CONTROL_VALUES.includes(control as CodegenControl) ? (control as CodegenControl) : 'input'
}

/** 按控件给默认列宽 */
function defaultWidth(control: CodegenControl): number {
  if (control === 'textarea') return 200
  if (control === 'switch') return 90
  if (control === 'datetime') return 170
  if (control === 'date') return 140
  if (control === 'number') return 110
  return 160
}

/** 按数据库类型推断控件 */
function inferControl(column: CodegenTableColumn): CodegenControl {
  if (column.max_length && column.max_length > 255) return 'textarea'
  const sqlType = column.sql_type.toLowerCase()
  if (/bool/.test(sqlType)) return 'switch'
  if (/(int|float|double|decimal|numeric)/.test(sqlType)) return 'number'
  if (/timestamp|datetime/.test(sqlType)) return 'datetime'
  if (/date/.test(sqlType)) return 'date'
  return 'input'
}

/** 表字段 → 默认字段配置 */
function defaultFieldConfig(column: CodegenTableColumn): CodegenFieldConfig {
  const control = inferControl(column)
  const hasDefault = column.default !== null && column.default !== undefined
  return {
    name: column.name,
    label: column.comment || column.name,
    control,
    required: !column.nullable && !hasDefault,
    searchable: !column.primary_key && control !== 'textarea',
    listable: control !== 'textarea',
    editable: !column.primary_key,
    dict_type: null,
    description: column.comment,
    width: defaultWidth(control),
  }
}

/** 建议结果 → 可编辑字段配置(缺省项按控件补齐) */
function normalizeSuggestedColumn(column: CodegenSuggestColumn): CodegenFieldConfig {
  const control = normalizeControl(column.control)
  return {
    name: column.name,
    label: column.label || column.name,
    control,
    required: Boolean(column.required),
    searchable: Boolean(column.searchable),
    listable: Boolean(column.listable),
    editable: Boolean(column.editable),
    dict_type: column.dict_type ?? null,
    // 后端契约 description 为字符串: 空值统一空串, 避免 null 触发 422
    description: column.description ?? '',
    width: column.width && column.width > 0 ? column.width : defaultWidth(control),
  }
}

/** 字段类型展示文案(用于表格字段列小字) */
function sqlTypeText(name: string): string {
  const meta = columnMeta.value[name]
  if (!meta) return ''
  return meta.max_length ? `${meta.sql_type}(${meta.max_length})` : meta.sql_type
}

/** 选中数据表: 读取表结构并初始化配置 */
async function handleSelectTable(table: CodegenTable) {
  // 先落选中态: 右侧立即显示加载遮罩, 避免等待期间仍是旧表配置
  selectedTable.value = { ...table }
  moduleName.value = table.name
  className.value = toPascalCase(table.name)
  pageTitle.value = table.comment || table.name
  columns.value = []
  columnMeta.value = {}
  warnings.value = []
  lastResult.value = null
  overwrite.value = false
  pickerVisible.value = false
  try {
    tableDetailLoading.value = true
    const detail = await getCodegenTable(table.name)
    selectedTable.value = {
      name: detail.name,
      comment: detail.comment,
      column_count: detail.columns.length,
    }
    moduleName.value = detail.name
    className.value = toPascalCase(detail.name)
    pageTitle.value = detail.comment || detail.name
    columns.value = detail.columns.map(defaultFieldConfig)
    columnMeta.value = Object.fromEntries(detail.columns.map((column) => [column.name, column]))
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    tableDetailLoading.value = false
  }
}

/** 智能建议: 应用 AI/模板推断结果 */
async function handleSuggest() {
  if (!selectedTable.value) {
    ElMessage.warning(t('cg_need_table'))
    return
  }
  try {
    suggestLoading.value = true
    const payload = {
      table_name: selectedTable.value.name,
      use_ai: useAi.value,
      module_name: moduleName.value.trim() || undefined,
      class_name: className.value.trim() || undefined,
    }
    const res = await suggestCodegen(payload)
    if (res.module_name) moduleName.value = res.module_name
    if (res.class_name) className.value = res.class_name
    if (res.page_title) pageTitle.value = res.page_title
    if (res.columns?.length) columns.value = res.columns.map(normalizeSuggestedColumn)
    warnings.value = res.warnings ?? []
    if (res.ai_used) ElMessage.success(t('cg_ai_used'))
    else ElMessage.warning(t('cg_ai_fallback'))
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    suggestLoading.value = false
  }
}

/** 构造预览/生成请求(统一校验) */
function buildPayload(): CodegenPreviewRequest | null {
  if (!selectedTable.value) {
    ElMessage.warning(t('cg_need_table'))
    return null
  }
  if (!moduleName.value.trim() || !className.value.trim()) {
    ElMessage.warning(t('cg_need_basic'))
    return null
  }
  return {
    table_name: selectedTable.value.name,
    module_name: moduleName.value.trim(),
    class_name: className.value.trim(),
    page_title: pageTitle.value.trim() || moduleName.value.trim(),
    columns: columns.value.map((column) => ({ ...column })),
    include_backend: includeBackend.value,
    include_frontend: includeFrontend.value,
  }
}

/** 预览: 拉取文件内容并打开对话框 */
async function handlePreview() {
  const payload = buildPayload()
  if (!payload) return
  try {
    previewLoading.value = true
    const res = await previewCodegen(payload)
    previewFiles.value = res.files ?? []
    previewWarnings.value = res.warnings ?? []
    activePreviewPath.value = previewFiles.value[0]?.path ?? ''
    copied.value = false
    previewVisible.value = true
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    previewLoading.value = false
  }
}

/** 生成: 按覆盖开关落盘, 并展示写入/跳过结果 */
async function handleGenerate() {
  const payload = buildPayload()
  if (!payload) return
  try {
    generateLoading.value = true
    const res = await generateCodegen({ ...payload, overwrite: overwrite.value })
    lastResult.value = res
    warnings.value = res.warnings ?? []
    previewVisible.value = false
    ElMessage.success(t('cg_written', { n: res.written.length }))
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    generateLoading.value = false
  }
}

/** 复制当前预览文件内容 */
async function handleCopy() {
  if (!activePreview.value) return
  const ok = await copyToClipboard(activePreview.value.content)
  if (!ok) {
    ElMessage.error(t('cg_error'))
    return
  }
  copied.value = true
  ElMessage.success(t('cg_copied'))
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
  }, 2000)
}

// 搜索框防抖(300ms), 回车/清空立即查询
watch(tableKeyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(fetchTables, 300)
})

onMounted(fetchTables)
onUnmounted(() => {
  if (keywordTimer) clearTimeout(keywordTimer)
  if (copyTimer) clearTimeout(copyTimer)
})
</script>
