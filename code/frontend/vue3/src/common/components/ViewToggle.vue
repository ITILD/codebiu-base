<!--
  通用视图切换(卡片 / 列表)
  用法:
    <ViewToggle v-model="view" />
    <ViewToggle v-model="view" card-label="卡片" list-label="列表" />
-->
<template>
  <div class="view-toggle" role="group" aria-label="视图切换">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="view-toggle-btn"
      :class="{ 'is-active': modelValue === opt.value }"
      :aria-pressed="modelValue === opt.value"
      :title="opt.label"
      @click="emit('update:modelValue', opt.value)"
    >
      <el-icon :size="14"><component :is="opt.icon" /></el-icon>
      <span class="view-toggle-label">{{ opt.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { Grid, Tickets } from '@element-plus/icons-vue'

type ViewMode = 'card' | 'list'

const props = withDefaults(
  defineProps<{
    modelValue: ViewMode
    cardLabel?: string
    listLabel?: string
  }>(),
  { cardLabel: '卡片', listLabel: '列表' }
)

const emit = defineEmits<{ (e: 'update:modelValue', value: ViewMode): void }>()

const options = computed(() => [
  { value: 'card' as ViewMode, label: props.cardLabel, icon: Grid },
  { value: 'list' as ViewMode, label: props.listLabel, icon: Tickets },
])
</script>

<style scoped>
.view-toggle {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border-radius: 9px;
  background: var(--note-soft);
}
.view-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--note-sub);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.view-toggle-btn:hover {
  color: var(--note-text);
}
.view-toggle-btn.is-active {
  background: rgb(var(--note-card-rgb));
  color: var(--note-green);
  font-weight: 600;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.06);
}
</style>
