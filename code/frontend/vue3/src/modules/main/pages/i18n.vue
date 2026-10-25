<template>
  <div p-4 md:p-6 w-full min-w-0 class="i18n-page">
    <!-- 水墨页头 -->
    <InkPageHead :title="t('i18n_title')" seal="译">
      <template #sub>{{ t('i18n_subtitle') }}</template>
    </InkPageHead>

    <div page-card>
      <el-tabs v-model="activeTab">
        <!-- ############ 词条覆盖 ############ -->
        <el-tab-pane :label="t('i18n_tab_overrides')" name="overrides">
          <!-- 工具栏: 搜索/新增/导入导出 + 覆盖开关 -->
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <el-input
              v-model="keyword"
              :placeholder="t('i18n_search_key')"
              :prefix-icon="Search"
              clearable
              class="!w-full sm:!w-56"
              :aria-label="t('i18n_search_key')"
            />
            <el-button type="primary" :icon="Plus" @click="addRow">
              {{ t('i18n_add') }}
            </el-button>
            <el-button :icon="Download" :loading="exporting" @click="handleExport">
              {{ t('i18n_export') }}
            </el-button>
            <el-button :icon="Upload" :loading="importing" @click="pickImportFile">
              {{ t('i18n_import') }}
            </el-button>
            <span class="flex items-center gap-1.5 text-xs text-note-sub sm:ml-auto">
              <el-switch v-model="importOverwrite" size="small" :aria-label="t('i18n_overwrite')" />
              {{ t('i18n_overwrite') }}
            </span>
            <!-- 隐藏文件选择: 导入 JSON -->
            <input
              ref="fileInput"
              type="file"
              accept=".json,application/json"
              class="hidden"
              @change="handleImportFile"
            />
          </div>

          <!-- 导入跳过的键名 -->
          <el-alert
            v-if="importSkipped.length"
            type="info"
            :closable="false"
            :title="t('i18n_skipped', { n: importSkipped.length })"
            class="mb-3"
          >
            <div class="flex flex-wrap gap-1">
              <el-tag v-for="key in importSkipped" :key="key" size="small" type="info">
                {{ key }}
              </el-tag>
            </div>
          </el-alert>

          <!-- 桌面/平板: 词条表格(横向滚动收在表格内部) -->
          <el-table v-if="isMd" v-loading="loading" :data="filteredRows" size="small" stripe>
            <el-table-column :label="t('i18n_key')" min-width="190">
              <template #default="{ row }">
                <el-input
                  v-if="row.isNew"
                  v-model="row.key"
                  size="small"
                  class="font-mono"
                  :placeholder="t('i18n_key')"
                  :aria-label="t('i18n_key')"
                  @blur="blurSave(row)"
                />
                <span v-else class="break-all font-mono text-xs">{{ row.key }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('i18n_zh')" min-width="170">
              <template #default="{ row }">
                <el-input
                  v-model="row.zh"
                  size="small"
                  :aria-label="`${row.key} ${t('i18n_zh')}`"
                  @blur="blurSave(row)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="t('i18n_ja')" min-width="170">
              <template #default="{ row }">
                <el-input
                  v-model="row.ja"
                  size="small"
                  :aria-label="`${row.key} ${t('i18n_ja')}`"
                  @blur="blurSave(row)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="t('i18n_en')" min-width="170">
              <template #default="{ row }">
                <el-input
                  v-model="row.en"
                  size="small"
                  :aria-label="`${row.key} ${t('i18n_en')}`"
                  @blur="blurSave(row)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="t('i18n_updated_at')" width="150">
              <template #default="{ row }">
                <span class="text-xs text-note-sub">{{ formatDateTime(row.updated_at) || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('pt_actions')" width="128" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" link :loading="row.saving" @click="saveRow(row)">
                  {{ t('i18n_save') }}
                </el-button>
                <el-button size="small" type="danger" link @click="handleDelete(row)">
                  {{ t('i18n_delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 手机: 每行改卡片 -->
          <div v-else v-loading="loading" class="flex flex-col gap-3">
            <div
              v-for="row in filteredRows"
              :key="row.isNew ? `new-${row.key}` : row.key"
              class="rounded-note-md border border-note bg-note-soft/60 p-3"
            >
              <div class="mb-2 flex items-start justify-between gap-2">
                <el-input
                  v-if="row.isNew"
                  v-model="row.key"
                  size="small"
                  class="min-w-0 flex-1 font-mono"
                  :placeholder="t('i18n_key')"
                  :aria-label="t('i18n_key')"
                  @blur="blurSave(row)"
                />
                <span v-else class="min-w-0 break-all font-mono text-xs text-note">{{ row.key }}</span>
                <div class="flex shrink-0 gap-1">
                  <el-button size="small" type="primary" link :loading="row.saving" @click="saveRow(row)">
                    {{ t('i18n_save') }}
                  </el-button>
                  <el-button size="small" type="danger" link @click="handleDelete(row)">
                    {{ t('i18n_delete') }}
                  </el-button>
                </div>
              </div>
              <div class="grid grid-cols-1 gap-2">
                <div v-for="field in languageFields" :key="field.prop">
                  <p class="mb-1 text-[11px] text-note-sub">{{ t(field.labelKey) }}</p>
                  <el-input
                    v-model="row[field.prop]"
                    size="small"
                    type="textarea"
                    :rows="2"
                    :aria-label="`${row.key} ${t(field.labelKey)}`"
                    @blur="blurSave(row)"
                  />
                </div>
              </div>
              <p class="mt-2 text-[11px] text-note-sub">
                {{ t('i18n_updated_at') }}: {{ formatDateTime(row.updated_at) || '—' }}
              </p>
            </div>
            <el-empty v-if="!filteredRows.length" :description="t('admin_no_data')" :image-size="72" />
          </div>
        </el-tab-pane>

        <!-- ############ 缺失检测 ############ -->
        <el-tab-pane :label="t('i18n_tab_missing')" name="missing">
          <div class="flex flex-col gap-3">
            <div class="flex flex-wrap items-center gap-2">
              <p class="min-w-[14rem] flex-1 text-xs leading-relaxed text-note-sub">
                {{ t('i18n_missing_desc') }}
              </p>
              <el-button type="primary" :icon="Search" :loading="scanning" @click="handleScan">
                {{ scanning ? t('i18n_scanning') : t('i18n_scan') }}
              </el-button>
            </div>

            <!-- 扫描统计 -->
            <div v-if="scanned" class="flex flex-wrap items-center gap-2">
              <el-tag type="danger">{{ t('i18n_missing_count', { n: missingList.length }) }}</el-tag>
              <el-tag type="info">{{ t('i18n_unused_count', { n: unusedKeys.length }) }}</el-tag>
            </div>

            <template v-if="scanned">
              <el-empty v-if="!missingList.length" :description="t('i18n_no_missing')" :image-size="72" />
              <ul v-else class="m-0 flex list-none flex-col gap-2 p-0">
                <li
                  v-for="item in missingList"
                  :key="item.key"
                  class="rounded-note-md border border-note bg-note-soft/60 p-3"
                >
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <span class="min-w-0 break-all font-mono text-xs text-note">{{ item.key }}</span>
                    <el-button
                      v-if="!filledKeys.has(item.key)"
                      size="small"
                      type="primary"
                      :loading="fillingKey === item.key"
                      @click="handleFillOne(item.key)"
                    >
                      {{ t('i18n_add_all') }}
                    </el-button>
                    <el-tag v-else size="small" type="success">{{ t('i18n_saved') }}</el-tag>
                  </div>
                  <p class="mt-1 break-all text-[11px] text-note-sub">
                    {{ t('i18n_source') }}: {{ item.sources.join(', ') }}
                  </p>
                </li>
              </ul>
            </template>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 多语言词条管理
 * 1) 词条覆盖: 在线维护 key → 三语覆盖表, 保存后运行时热更新
 * 2) 缺失检测: 扫描源码中的静态 t() 键, 与 languageObj 比对, 支持一键补齐中文
 */
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search, Upload } from '@element-plus/icons-vue'
import { applyI18nOverrides, i18n, languageObj } from '@/common/i18n/language'
import { useResponsive } from '@/common/composables/useResponsive'
import { triggerBlobDownload } from '@/common/utils/export'
import { formatDateTime } from '@/common/utils/datetime'
import {
  deleteI18nOverride,
  exportI18nEntries,
  importI18nEntries,
  listI18nOverrides,
  saveI18nOverrides,
} from '../api/i18n'
import type { I18nEntry } from '../types/i18n'

const { t } = i18n.global
const { isMd } = useResponsive()

/** 可编辑行(新增行标记 + 保存态) */
interface OverrideRow {
  key: string
  zh: string
  ja: string
  en: string
  updated_at: string
  /** 新增尚未落库的行 */
  isNew?: boolean
  /** 正在保存 */
  saving?: boolean
}

/** 三语字段元数据(移动端卡片遍历用) */
const languageFields: { labelKey: 'i18n_zh' | 'i18n_ja' | 'i18n_en'; prop: 'zh' | 'ja' | 'en' }[] = [
  { labelKey: 'i18n_zh', prop: 'zh' },
  { labelKey: 'i18n_ja', prop: 'ja' },
  { labelKey: 'i18n_en', prop: 'en' },
]

const activeTab = ref<'overrides' | 'missing'>('overrides')

// ################ 词条覆盖 ################
const rows = ref<OverrideRow[]>([])
const loading = ref(false)
const keyword = ref('')
const exporting = ref(false)
const importing = ref(false)
const importOverwrite = ref(false)
const importSkipped = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
/** 已落库内容的签名, 用于失焦时跳过无改动的保存 */
const snapshots = new Map<string, string>()

const filteredRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return kw ? rows.value.filter((row) => row.key.toLowerCase().includes(kw)) : rows.value
})

/** 行内容签名(判断是否有改动) */
function signature(row: { zh: string; ja: string; en: string }): string {
  return JSON.stringify([row.zh, row.ja, row.en])
}

/** 统一错误文案: 优先后端返回信息 */
function errorText(error: unknown): string {
  return error instanceof Error && error.message ? error.message : t('i18n_error')
}

/** 拉取覆盖表并重建签名快照 */
async function fetchOverrides() {
  try {
    loading.value = true
    const list = await listI18nOverrides()
    rows.value = (list ?? []).map((item) => ({
      key: item.key,
      zh: item.zh ?? '',
      ja: item.ja ?? '',
      en: item.en ?? '',
      updated_at: item.updated_at,
    }))
    snapshots.clear()
    for (const row of rows.value) snapshots.set(row.key, signature(row))
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    loading.value = false
  }
}

/** 新增空行(置于顶部并进入行内编辑) */
function addRow() {
  if (rows.value.some((row) => row.isNew && !row.key.trim())) {
    ElMessage.warning(t('i18n_need_key'))
    return
  }
  keyword.value = ''
  rows.value.unshift({ key: '', zh: '', ja: '', en: '', updated_at: '', isNew: true })
}

/** 失焦保存: 新增行不自动保存, 避免填 key 后失焦就把空值落库并重载行(丢弃后续输入) */
function blurSave(row: OverrideRow) {
  if (row.isNew) return
  saveRow(row)
}

/** 保存单行(失焦或点击保存触发; 无改动直接跳过) */
async function saveRow(row: OverrideRow) {
  const key = row.key.trim()
  if (!key) {
    ElMessage.warning(t('i18n_need_key'))
    return
  }
  if (row.isNew && rows.value.some((item) => item !== row && item.key === key)) {
    ElMessage.warning(t('i18n_key_exists'))
    return
  }
  if (row.saving) return
  if (!row.isNew && snapshots.get(key) === signature(row)) return

  try {
    row.saving = true
    await saveI18nOverrides([{ key, zh: row.zh, ja: row.ja, en: row.en }])
    snapshots.set(key, signature(row))
    // 保存后立即热更新当前运行的词条
    applyI18nOverrides({ [key]: [row.zh, row.ja, row.en] })
    ElMessage.success(t('i18n_saved'))
    if (row.isNew) await fetchOverrides()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    row.saving = false
  }
}

/** 删除词条(新增行直接本地移除, 已落库行二次确认) */
async function handleDelete(row: OverrideRow) {
  if (row.isNew) {
    rows.value = rows.value.filter((item) => item !== row)
    return
  }
  try {
    await ElMessageBox.confirm(`${t('i18n_delete')} ${row.key}?`, t('i18n_delete'), {
      type: 'warning',
      confirmButtonText: t('i18n_delete'),
      cancelButtonText: t('pt_cancel'),
    })
    await deleteI18nOverride(row.key)
    rows.value = rows.value.filter((item) => item.key !== row.key)
    snapshots.delete(row.key)
    importSkipped.value = importSkipped.value.filter((key) => key !== row.key)
    ElMessage.success(t('i18n_saved'))
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorText(error))
  }
}

/** 导出 JSON: 下载后端导出的完整词条 */
async function handleExport() {
  try {
    exporting.value = true
    const res = await exportI18nEntries()
    const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
    triggerBlobDownload(blob, `i18n-${new Date().toISOString().slice(0, 10)}.json`)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    exporting.value = false
  }
}

/** 打开系统文件选择器 */
function pickImportFile() {
  fileInput.value?.click()
}

/** 解析导入 JSON(兼容数组与 { items: [...] } 两种结构) */
function parseImportItems(raw: unknown): I18nEntry[] {
  const source = Array.isArray(raw)
    ? raw
    : raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items)
      ? ((raw as { items: unknown[] }).items)
      : []
  return source.flatMap((entry): I18nEntry[] => {
    if (!entry || typeof entry !== 'object') return []
    const record = entry as Record<string, unknown>
    const key = typeof record.key === 'string' ? record.key.trim() : ''
    if (!key) return []
    const pick = (field: string) => (typeof record[field] === 'string' ? (record[field] as string) : '')
    return [{ key, zh: pick('zh'), ja: pick('ja'), en: pick('en') }]
  })
}

/** 导入 JSON 文件 */
async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // 清空值以允许重复选择同一文件
  input.value = ''
  if (!file) return

  try {
    importing.value = true
    const raw = JSON.parse(await file.text()) as unknown
    const items = parseImportItems(raw)
    if (!items.length) {
      ElMessage.error(t('i18n_error'))
      return
    }
    const res = await importI18nEntries(items, importOverwrite.value)
    importSkipped.value = res.skipped ?? []
    ElMessage.success(t('i18n_imported', { n: res.count }))
    await fetchOverrides()
  } catch (error) {
    ElMessage.error(error instanceof SyntaxError ? t('i18n_error') : errorText(error))
  } finally {
    importing.value = false
  }
}

// ################ 缺失检测 ################
/** 懒加载全部源码原文(vue/ts), 扫描静态 t() 键 */
const RAW_SOURCES = import.meta.glob<string>('/src/**/*.{vue,ts}', {
  query: '?raw',
  import: 'default',
})
/** 静态取词: 直接调用取词函数且参数为带引号字面量; 模板字符串动态键不匹配 */
const KEY_PATTERN = /\bt\(\s*(['"])([^'"\n]+)\1/g

const scanned = ref(false)
const scanning = ref(false)
const missingList = ref<{ key: string; sources: string[] }[]>([])
const unusedKeys = ref<string[]>([])
const filledKeys = ref<Set<string>>(new Set())
const fillingKey = ref('')

/** 扫描源码并比对 languageObj 的键集合 */
async function handleScan() {
  try {
    scanning.value = true
    scanned.value = false
    const defined = new Set(Object.keys(languageObj))
    const used = new Map<string, Set<string>>()

    for (const [path, load] of Object.entries(RAW_SOURCES)) {
      let content = ''
      try {
        content = await load()
      } catch {
        continue
      }
      for (const match of content.matchAll(KEY_PATTERN)) {
        const key = match[2]?.trim()
        if (!key || key.includes('${')) continue
        if (!used.has(key)) used.set(key, new Set())
        used.get(key)!.add(path.replace(/^\/src\//, ''))
      }
    }

    missingList.value = [...used.entries()]
      .filter(([key]) => !defined.has(key))
      .map(([key, sources]) => ({ key, sources: [...sources] }))
      .sort((a, b) => a.key.localeCompare(b.key))
    unusedKeys.value = [...defined].filter((key) => !used.has(key)).sort()
    scanned.value = true
  } finally {
    scanning.value = false
  }
}

/** 一键补齐: 以键名作为中文写入覆盖表, 并热更新 */
async function handleFillOne(key: string) {
  try {
    fillingKey.value = key
    await saveI18nOverrides([{ key, zh: key }])
    filledKeys.value.add(key)
    applyI18nOverrides({ [key]: [key, '', ''] })
    ElMessage.success(t('i18n_saved'))
    await fetchOverrides()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    fillingKey.value = ''
  }
}

onMounted(fetchOverrides)
</script>
