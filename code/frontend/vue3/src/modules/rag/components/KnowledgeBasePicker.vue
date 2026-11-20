<!--
  知识库范围选择器(问答输入区)
  三态: 自动(auto, 未勾选时后端自动匹配有权限的知识库) / 手动(manual, 仅勾选项) / 禁用(off)
  用法:
    <KnowledgeBasePicker
      v-model="selectedProjectIds"
      v-model:mode="kbMode"
      :projects="myProjects"
      :disabled="isSending"
    />
-->
<template>
  <el-popover
    v-model:visible="visible"
    trigger="click"
    placement="top-start"
    :width="420"
    :disabled="disabled"
    popper-class="kbp-popper"
    popper-style="padding: 0; border-radius: 14px; overflow: hidden;"
  >
    <template #reference>
      <button
        type="button"
        class="kbp-trigger"
        :class="{ 'is-active': visible || selectedCount > 0 || mode !== 'off' }"
        :disabled="disabled"
        :title="triggerTitle"
        aria-label="选择知识库"
      >
        <el-icon :size="14"><Collection /></el-icon>
        <span class="kbp-trigger-text">{{ triggerLabel }}</span>
        <el-icon :size="10" class="kbp-trigger-arrow"><CaretBottom /></el-icon>
      </button>
    </template>

    <div class="kbp-panel">
      <!-- 头部: 标题 + 三态切换 -->
      <div class="kbp-head">
        <div class="kbp-head-row">
          <span class="kbp-title">知识库范围</span>
          <span class="kbp-sub">{{ panelSubLabel }}</span>
        </div>
        <div class="kbp-tabs" role="group" aria-label="知识库范围">
          <button
            v-for="opt in SCOPE_OPTIONS"
            :key="opt.key"
            type="button"
            class="kbp-tab"
            :class="{ 'is-active': mode === opt.key }"
            @click="changeMode(opt.key)"
          >
            {{ opt.label }}
          </button>
        </div>
        <p class="kbp-note">{{ SCOPE_NOTE[mode] }}</p>
        <label class="kbp-search">
          <el-icon :size="13" class="kbp-search-icon"><Search /></el-icon>
          <input
            v-model="keyword"
            type="text"
            class="kbp-search-input"
            placeholder="搜索知识库名称"
          />
        </label>
      </div>

      <!-- 列表: 勾选 = 限定检索范围(自动模式下为优先范围) -->
      <div class="kbp-list">
        <!-- 个人问答知识库: 问答附件自动入库于此, 非禁用态固定勾选(不可取消) -->
        <button
          v-if="personalKb"
          type="button"
          class="kbp-item kbp-item-locked"
          :class="{ 'is-checked': mode !== 'off', 'is-locked-off': mode === 'off' }"
          :title="
            mode === 'off'
              ? '知识库已禁用：个人问答知识库本轮不参与检索，附件上传不可用'
              : '个人问答知识库：问答附件自动入库，固定参与检索（不可取消）'
          "
          @click.prevent
        >
          <span class="kbp-check">
            <el-icon v-if="mode !== 'off'" :size="11"><Check /></el-icon>
          </span>
          <span class="kbp-item-main">
            <span class="kbp-item-name">{{ personalKb.project_name }}</span>
            <span class="kbp-item-desc">
              {{ mode === 'off' ? '知识库已禁用，本轮不检索' : '问答附件自动入库，固定参与检索' }}
            </span>
          </span>
          <el-tag size="small" effect="plain" type="success">问答</el-tag>
        </button>
        <button
          v-for="p in filteredProjects"
          :key="p.project_id"
          type="button"
          class="kbp-item"
          :class="{ 'is-checked': selectedIds.has(p.project_id) }"
          @click="toggleItem(p.project_id)"
        >
          <span class="kbp-check">
            <el-icon v-if="selectedIds.has(p.project_id)" :size="11"><Check /></el-icon>
          </span>
          <span class="kbp-item-main">
            <span class="kbp-item-name">{{ p.project_name }}</span>
            <span class="kbp-item-desc">{{ p.project_description || '暂无描述' }}</span>
          </span>
          <el-tag size="small" effect="plain" type="info">
            {{ p.is_private ? '私有' : '公开' }}
          </el-tag>
        </button>
        <p v-if="filteredProjects.length === 0" class="kbp-empty">
          {{ keyword ? '没有匹配的知识库' : personalKb ? '暂无其它知识库' : '暂无可访问的知识库' }}
        </p>
      </div>

      <!-- 底部: 汇总 + 清空 -->
      <div class="kbp-foot">
        <span class="kbp-foot-text">{{ footLabel }}</span>
        <button
          v-if="selectedCount > 0"
          type="button"
          class="kbp-clear"
          @click="clearSelection"
        >
          清空勾选
        </button>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { CaretBottom, Check, Collection, Search } from '@element-plus/icons-vue'
import type { MyProject } from '../types'

/** 知识库范围三态 */
type KbMode = 'auto' | 'manual' | 'off'

const props = withDefaults(
  defineProps<{
    /** 已勾选的知识库项目 ID */
    modelValue: string[]
    /** 范围模式: auto/manual/off */
    mode?: KbMode
    /** 可访问的知识库项目 */
    projects?: MyProject[]
    /** 个人问答知识库(问答附件入库, 非禁用态固定勾选且不可取消) */
    personalKb?: MyProject | null
    disabled?: boolean
  }>(),
  { mode: 'auto', projects: () => [], personalKb: null, disabled: false }
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
  (e: 'update:mode', value: KbMode): void
}>()

const SCOPE_OPTIONS: { key: KbMode; label: string }[] = [
  { key: 'auto', label: '自动' },
  { key: 'manual', label: '手动' },
  { key: 'off', label: '禁用' },
]

/** 三态说明文案(与后端语义一致) */
const SCOPE_NOTE: Record<KbMode, string> = {
  auto: '自动匹配你有权限的知识库；勾选后优先在这些知识库内检索。',
  manual: '仅检索勾选的知识库；未勾选时本轮不检索知识库。',
  off: '本轮不检索任何知识库，仅使用对话模型直接回答；附件上传不可用。',
}

const visible = ref(false)
const keyword = ref('')

const selectedIds = computed(() => new Set(props.modelValue))
const selectedCount = computed(() => props.modelValue.length)
/** 实际生效的知识库数(个人问答知识库在非禁用态固定勾选) */
const checkedTotal = computed(
  () => selectedCount.value + (props.personalKb && props.mode !== 'off' ? 1 : 0)
)

/** 个人问答知识库单独置顶展示, 不参与搜索过滤, 避免被列表筛掉 */
const filteredProjects = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  const personalId = props.personalKb?.project_id
  const rest = props.projects.filter((p) => p.project_id !== personalId)
  if (!kw) return rest
  return rest.filter(
    (p) =>
      p.project_name.toLowerCase().includes(kw) ||
      (p.project_description || '').toLowerCase().includes(kw)
  )
})

const triggerLabel = computed(() => {
  if (props.mode === 'off') return '知识库已禁用'
  if (checkedTotal.value > 0) return `知识库 ${checkedTotal.value}`
  if (props.mode === 'auto') return '知识库 · 自动'
  return '知识库 · 未选'
})

const triggerTitle = computed(() => {
  if (props.mode === 'off') return '本轮禁用知识库检索，点击可调整'
  if (checkedTotal.value > 0) return `已勾选 ${checkedTotal.value} 个知识库，点击调整`
  return props.mode === 'auto'
    ? '自动匹配有权限的知识库，点击可手动指定'
    : '未指定知识库，点击选择'
})

const panelSubLabel = computed(() =>
  props.projects.length ? `共 ${props.projects.length} 个可访问` : '无可访问知识库'
)

const footLabel = computed(() => {
  if (props.mode === 'off') return '已禁用知识库检索（附件上传不可用）'
  const personal = props.personalKb ? '（含个人问答知识库）' : ''
  if (selectedCount.value > 0) return `已勾选 ${checkedTotal.value} 个知识库${personal}`
  return props.mode === 'auto'
    ? `未勾选：检索范围为本账号全部有权限的知识库${personal}`
    : `未勾选：仅使用问答知识库${personal}`
})

/** 切换三态 */
const changeMode = (mode: KbMode) => {
  emit('update:mode', mode)
}

/** 勾选/取消: 禁用态下勾选自动恢复为手动模式 */
const toggleItem = (projectId: string) => {
  const next = new Set(props.modelValue)
  if (next.has(projectId)) next.delete(projectId)
  else {
    next.add(projectId)
    if (props.mode === 'off') emit('update:mode', 'manual')
  }
  emit('update:modelValue', [...next])
}

const clearSelection = () => emit('update:modelValue', [])
</script>

<style scoped>
.kbp-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: var(--note-tint);
  color: var(--note-sub);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.18s ease;
}
.kbp-trigger:hover {
  color: var(--note-text);
}
.kbp-trigger.is-active {
  background: rgb(var(--note-card-rgb));
  border-color: rgb(var(--note-green-rgb, 74 124 89) / 0.35);
  color: var(--note-green);
}
.kbp-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.kbp-trigger-arrow {
  opacity: 0.5;
}
.kbp-panel {
  display: flex;
  flex-direction: column;
  max-height: 460px;
}
.kbp-head {
  padding: 12px 14px 10px;
  border-bottom: 1px solid var(--note-soft);
}
.kbp-head-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.kbp-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--note-text);
}
.kbp-sub {
  font-size: 11px;
  color: var(--note-sub);
}
.kbp-tabs {
  display: flex;
  gap: 4px;
  margin-top: 10px;
  padding: 3px;
  border-radius: 9px;
  background: var(--note-soft);
}
.kbp-tab {
  flex: 1;
  padding: 5px 0;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--note-sub);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.kbp-tab.is-active {
  background: rgb(var(--note-card-rgb));
  color: var(--note-green);
  font-weight: 600;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.06);
}
.kbp-note {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--note-sub);
}
.kbp-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 0 10px;
  height: 30px;
  border-radius: 8px;
  background: var(--note-soft);
}
.kbp-search-icon {
  color: var(--note-sub);
  flex-shrink: 0;
}
.kbp-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 12px;
  color: var(--note-text);
}
.kbp-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}
.kbp-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 9px;
  border: none;
  border-radius: 9px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease;
}
.kbp-item:hover {
  background: var(--note-soft);
}
.kbp-item.is-checked {
  background: var(--note-tint);
}
/* 个人问答知识库: 固定勾选项(非禁用态不可取消) */
.kbp-item-locked {
  cursor: default;
  margin-bottom: 2px;
  border-bottom: 1px dashed var(--note-soft);
  border-radius: 9px 9px 0 0;
}
.kbp-item-locked.is-locked-off {
  opacity: 0.55;
}
.kbp-check {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 5px;
  border: 1px solid var(--note-border);
  color: #fff;
  flex-shrink: 0;
}
.kbp-item.is-checked .kbp-check {
  background: var(--note-green);
  border-color: var(--note-green);
}
.kbp-item-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.kbp-item-name {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--note-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kbp-item-desc {
  font-size: 11px;
  color: var(--note-sub);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kbp-empty {
  margin: 0;
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  color: var(--note-sub);
}
.kbp-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 14px;
  height: 40px;
  border-top: 1px solid var(--note-soft);
}
.kbp-foot-text {
  font-size: 11px;
  color: var(--note-sub);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kbp-clear {
  border: none;
  background: transparent;
  color: var(--note-green);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
</style>
