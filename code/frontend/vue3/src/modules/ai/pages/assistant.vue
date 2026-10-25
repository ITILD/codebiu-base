<!-- AI 助手配置页: 展示形态、默认对话参数、欢迎语/快捷提问、快捷入口 -->
<template>
  <div class="flex w-full min-w-0 flex-col gap-4 p-4 md:p-6">
    <!-- 水墨页头 -->
    <InkPageHead :title="t('asst_title')" seal="助">
      <template #sub>{{ t('asst_subtitle') }}</template>
    </InkPageHead>

    <!-- 顶部操作条: 保存 / 恢复默认 -->
    <div class="flex flex-wrap items-center justify-end gap-2">
      <el-button
        class="min-h-11 w-full sm:w-auto"
        :icon="RefreshLeft"
        :aria-label="t('asst_reset')"
        @click="handleReset"
      >
        {{ t('asst_reset') }}
      </el-button>
      <el-button
        type="primary"
        class="min-h-11 w-full sm:w-auto"
        :icon="Check"
        :aria-label="t('asst_save')"
        @click="handleSave"
      >
        {{ t('asst_save') }}
      </el-button>
    </div>

    <!-- 四个配置区块: 桌面两列, 窄屏单列 -->
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <!-- ############ 展示形态 ############ -->
      <div class="page-card min-w-0">
        <div class="card-toolbar">
          <h3 class="font-bold text-note">{{ t('asst_display') }}</h3>
        </div>

        <div class="flex flex-col gap-4">
          <!-- 悬浮助手开关 -->
          <div class="flex min-h-11 items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-sm text-note">{{ t('asst_float_enable') }}</p>
              <p class="mt-0.5 text-xs leading-relaxed text-note-sub">
                {{ t('asst_float_enable_hint') }}
              </p>
            </div>
            <el-switch
              v-model="draft.enabled"
              class="shrink-0"
              :aria-label="t('asst_float_enable')"
            />
          </div>

          <!-- 自动弹开开关 -->
          <div class="flex min-h-11 items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="text-sm text-note">{{ t('asst_auto_open') }}</p>
              <p class="mt-0.5 text-xs leading-relaxed text-note-sub">
                {{ t('asst_auto_open_hint') }}
              </p>
            </div>
            <el-switch
              v-model="draft.autoOpen"
              class="shrink-0"
              :aria-label="t('asst_auto_open')"
            />
          </div>

          <!-- 悬浮按钮位置 -->
          <div>
            <p class="mb-1 text-xs text-note-sub">{{ t('asst_position') }}</p>
            <div class="flex min-h-11 items-center">
              <el-radio-group v-model="draft.position" :aria-label="t('asst_position')">
                <el-radio-button value="right">{{ t('asst_position_right') }}</el-radio-button>
                <el-radio-button value="left">{{ t('asst_position_left') }}</el-radio-button>
              </el-radio-group>
            </div>
          </div>
        </div>
      </div>

      <!-- ############ 默认对话参数 ############ -->
      <div class="page-card min-w-0">
        <div class="card-toolbar">
          <h3 class="font-bold text-note">{{ t('asst_defaults') }}</h3>
        </div>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <!-- 默认助手 -->
          <div class="min-w-0">
            <p class="mb-1 text-xs text-note-sub">{{ t('asst_default_agent') }}</p>
            <el-select
              v-model="draft.agentId"
              class="!w-full"
              filterable
              :aria-label="t('asst_default_agent')"
            >
              <el-option :label="t('asst_no_agent')" value="" />
              <el-option
                v-for="agent in agents"
                :key="agent.id"
                :label="agent.name"
                :value="agent.id"
              />
            </el-select>
          </div>

          <!-- 默认知识库(多选) -->
          <div class="min-w-0">
            <p class="mb-1 text-xs text-note-sub">{{ t('asst_default_kb') }}</p>
            <el-select
              v-model="draft.projectIds"
              class="!w-full"
              multiple
              collapse-tags
              collapse-tags-tooltip
              :aria-label="t('asst_default_kb')"
            >
              <el-option
                v-for="project in projects"
                :key="project.project_id"
                :label="project.project_name"
                :value="project.project_id"
              />
            </el-select>
          </div>

          <!-- 默认深度思考 -->
          <div
            class="flex min-h-11 items-center justify-between gap-2 rounded-note-md border border-note bg-note-soft/60 px-3 py-2"
          >
            <span class="text-sm text-note">{{ t('asst_deep_thinking') }}</span>
            <el-switch
              v-model="draft.deepThinking"
              :aria-label="t('asst_deep_thinking')"
            />
          </div>

          <!-- 默认联网搜索 -->
          <div
            class="flex min-h-11 items-center justify-between gap-2 rounded-note-md border border-note bg-note-soft/60 px-3 py-2"
          >
            <span class="text-sm text-note">{{ t('asst_websearch') }}</span>
            <el-switch
              v-model="draft.enableWebsearch"
              :aria-label="t('asst_websearch')"
            />
          </div>
        </div>
      </div>

      <!-- ############ 欢迎语与快捷提问 ############ -->
      <div class="page-card min-w-0">
        <div class="card-toolbar">
          <h3 class="font-bold text-note">{{ t('asst_welcome') }}</h3>
          <span class="text-[11px] text-note-sub">
            {{ draft.suggestions.length }}/{{ ASSISTANT_MAX_SUGGESTIONS }}
          </span>
        </div>

        <div class="flex flex-col gap-3">
          <!-- 欢迎语 -->
          <div>
            <p class="mb-1 text-xs text-note-sub">{{ t('asst_greeting') }}</p>
            <el-input
              v-model="draft.greeting"
              type="textarea"
              :rows="3"
              :placeholder="t('asst_greeting_ph')"
              :aria-label="t('asst_greeting')"
            />
          </div>

          <!-- 快捷提问列表 -->
          <div>
            <p class="mb-1 text-xs text-note-sub">{{ t('asst_suggestions') }}</p>
            <div class="flex flex-col gap-2">
              <!-- 按索引遍历: 输入过程中 key 稳定, 不会因文本变化丢失焦点 -->
              <div
                v-for="index in draft.suggestions.length"
                :key="index"
                class="flex items-center gap-2"
              >
                <el-input
                  v-model="draft.suggestions[index - 1]"
                  class="min-w-0 flex-1"
                  :placeholder="t('asst_suggestion_ph')"
                  :aria-label="`${t('asst_suggestions')} ${index}`"
                />
                <el-button
                  class="min-h-11 min-w-11 shrink-0"
                  :icon="Delete"
                  :aria-label="`${t('asst_remove')} ${index}`"
                  @click="removeSuggestion(index - 1)"
                />
              </div>

              <!-- 空状态提示 -->
              <p
                v-if="!draft.suggestions.length"
                class="rounded-note-md border border-dashed border-note bg-note-soft/60 px-3 py-2 text-xs text-note-sub"
              >
                {{ t('asst_suggestion_ph') }}
              </p>

              <!-- 添加快捷提问(达到上限禁用) -->
              <el-button
                class="min-h-11 w-full sm:w-auto"
                :icon="Plus"
                :disabled="draft.suggestions.length >= ASSISTANT_MAX_SUGGESTIONS"
                :aria-label="t('asst_add_suggestion')"
                @click="addSuggestion"
              >
                {{ t('asst_add_suggestion') }}
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- ############ 快捷入口 ############ -->
      <div class="page-card min-w-0">
        <div class="card-toolbar">
          <h3 class="font-bold text-note">{{ t('asst_entries') }}</h3>
        </div>

        <div class="flex flex-col gap-2">
          <button
            v-for="entry in entries"
            :key="entry.path"
            type="button"
            class="note-transition flex min-h-11 w-full items-center gap-3 rounded-note-md border border-note bg-note-soft/60 px-3 py-2.5 text-left hover:bg-note-tint hover:shadow-note focus-visible:outline-2 focus-visible:outline-offset-2"
            :aria-label="`${t(entry.titleKey)}: ${t(entry.descKey)}`"
            @click="openEntry(entry.path)"
          >
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-note-sm bg-note-tint text-note-green"
            >
              <el-icon :size="18"><component :is="entry.icon" /></el-icon>
            </span>
            <span class="min-w-0">
              <span v-ellipsis class="block truncate text-sm font-medium text-note">
                {{ t(entry.titleKey) }}
              </span>
              <span v-ellipsis:2 class="block text-xs leading-relaxed text-note-sub">
                {{ t(entry.descKey) }}
              </span>
            </span>
          </button>
        </div>
      </div>
    </div>

    <!-- 底部: 模型绑定提示(跳转账户设置) + 保存 / 恢复默认 -->
    <div class="page-card">
      <div class="card-toolbar !mb-0">
        <RouterLink
          to="/setting"
          class="note-transition flex min-h-11 min-w-0 items-center gap-1.5 text-xs leading-relaxed text-note-sub hover:text-note-green focus-visible:outline-2 focus-visible:outline-offset-2"
          :aria-label="t('asst_model_hint')"
        >
          <el-icon :size="14" class="shrink-0"><Setting /></el-icon>
          <span class="min-w-0">{{ t('asst_model_hint') }}</span>
        </RouterLink>

        <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <el-button
            class="min-h-11 w-full sm:w-auto"
            :icon="RefreshLeft"
            :aria-label="t('asst_reset')"
            @click="handleReset"
          >
            {{ t('asst_reset') }}
          </el-button>
          <el-button
            type="primary"
            class="min-h-11 w-full sm:w-auto"
            :icon="Check"
            :aria-label="t('asst_save')"
            @click="handleSave"
          >
            {{ t('asst_save') }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AI 助手配置页(后台)
 * - 展示形态: 悬浮入口启用/自动弹开/按钮位置
 * - 默认对话参数: 助手、知识库、深度思考、联网搜索
 * - 欢迎语与快捷提问: 保存后悬浮入口即时生效
 * - 快捷入口: 跳转对话/知识库管理/智能体编排
 * 表单一律绑定本地草稿 draft, 未保存的修改不影响响应式单例
 */
import { markRaw, type Component } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Check,
  Collection,
  Delete,
  MagicStick,
  Plus,
  RefreshLeft,
  Setting,
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { i18n } from '@/common/i18n/language'
import { listAgents } from '@/modules/agent/api/agent'
import type { AgentInfo } from '@/modules/agent/types'
import { listMyProjects } from '@/modules/rag/api/member'
import type { MyProject } from '@/modules/rag/types'
import {
  ASSISTANT_MAX_SUGGESTIONS,
  assistantConfig,
  resetAssistantConfig,
  saveAssistantConfig,
  type AssistantWidgetConfig,
} from '../utils/assistantConfig'

const { t } = i18n.global
const router = useRouter()

/** 深拷贝配置: 避免草稿与单例共享数组引用 */
function cloneConfig(source: AssistantWidgetConfig): AssistantWidgetConfig {
  return {
    ...source,
    projectIds: [...source.projectIds],
    suggestions: [...source.suggestions],
  }
}

/** 本地草稿(所有表单绑定它, 未保存不生效) */
const draft = ref<AssistantWidgetConfig>(cloneConfig(assistantConfig.value))

/** 可选助手 / 知识库(加载失败时保持空列表) */
const agents = ref<AgentInfo[]>([])
const projects = ref<MyProject[]>([])

/** 快捷入口定义 */
interface EntryItem {
  path: string
  titleKey: 'asst_entry_chat' | 'asst_entry_kb' | 'asst_entry_agent'
  descKey: 'asst_entry_chat_desc' | 'asst_entry_kb_desc' | 'asst_entry_agent_desc'
  icon: Component
}

const entries: EntryItem[] = [
  {
    path: '/rag/conversation',
    titleKey: 'asst_entry_chat',
    descKey: 'asst_entry_chat_desc',
    icon: markRaw(ChatDotRound),
  },
  {
    path: '/rag/project',
    titleKey: 'asst_entry_kb',
    descKey: 'asst_entry_kb_desc',
    icon: markRaw(Collection),
  },
  {
    path: '/agent/manage',
    titleKey: 'asst_entry_agent',
    descKey: 'asst_entry_agent_desc',
    icon: markRaw(MagicStick),
  },
]

/** 保存配置: 写入本地并同步悬浮入口单例 */
function handleSave() {
  saveAssistantConfig(draft.value)
  ElMessage.success(t('asst_saved'))
}

/** 恢复默认: 重置单例并重新克隆草稿 */
function handleReset() {
  resetAssistantConfig()
  draft.value = cloneConfig(assistantConfig.value)
  ElMessage.success(t('asst_reset_done'))
}

/** 添加快捷提问(达到上限时忽略) */
function addSuggestion() {
  if (draft.value.suggestions.length >= ASSISTANT_MAX_SUGGESTIONS) return
  draft.value.suggestions.push('')
}

/** 移除指定快捷提问 */
function removeSuggestion(index: number) {
  draft.value.suggestions.splice(index, 1)
}

/** 跳转快捷入口 */
function openEntry(path: string) {
  router.push(path)
}

/** 加载可选助手(失败静默, 保持空列表) */
async function loadAgents() {
  try {
    agents.value = await listAgents()
  } catch (error) {
    console.error('加载助手列表失败', error)
  }
}

/** 加载可选知识库(失败静默, 保持空列表) */
async function loadProjects() {
  try {
    const res = await listMyProjects({ page: 1, size: 200 })
    projects.value = res.items ?? []
  } catch (error) {
    console.error('加载知识库列表失败', error)
  }
}

onMounted(async () => {
  // 并行加载助手与知识库候选, 任一失败由各自函数内部静默处理
  await Promise.all([loadAgents(), loadProjects()])
})
</script>
