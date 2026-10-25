<template>
  <!-- 输入限制度量条: 已输入 / 限制 + 细进度条(淡雅配色, 超限转红) -->
  <div class="min-w-0 flex flex-col gap-1" role="group" :aria-label="ariaLabel">
    <div class="flex items-center gap-1.5 text-xs select-none">
      <span v-if="label" class="text-note-sub">{{ label }}</span>
      <span class="tabular-nums" :style="{ color: tone.color }">
        {{ usedText }}<template v-if="limit > 0"> / {{ limitText }}</template>
        <template v-else> {{ unitText }}</template>
      </span>
      <span v-if="limit > 0" class="tabular-nums text-xs" :style="{ color: tone.hint }">
        {{ over ? `超出 ${overText}` : `剩余 ${remainingText}` }}
      </span>
    </div>
    <div
      v-if="limit > 0"
      class="h-1 w-full overflow-hidden rounded-full"
      style="background: #e8efe7"
      role="progressbar"
      :aria-valuenow="used"
      :aria-valuemin="0"
      :aria-valuemax="limit"
      :aria-label="ariaLabel"
    >
      <div class="h-full rounded-full note-transition" :style="{ width, background: tone.bar }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 当前已输入用量 */
    used: number
    /** 限制总量(0 表示不限) */
    limit: number
    /** 计量单位: token / 字节 / 秒 */
    unit?: 'token' | 'bytes' | 'seconds'
    /** 左侧说明文案, 如 "输入上下文" */
    label?: string
  }>(),
  { unit: 'token', label: '' }
)

const unitText = computed(() =>
  props.unit === 'bytes' ? 'MB' : props.unit === 'seconds' ? '秒' : 'tokens'
)

/** 字节单位按 MB 展示(保留 1 位), 其余千分位整数 */
const fmt = (v: number): string =>
  props.unit === 'bytes'
    ? (v / 1024 / 1024).toFixed(1)
    : Math.round(v).toLocaleString('en-US')

const usedText = computed(() => fmt(props.used))
const limitText = computed(() => fmt(props.limit))
const remainingText = computed(() => fmt(Math.max(0, props.limit - props.used)))
const overText = computed(() => fmt(Math.max(0, props.used - props.limit)))

const ratio = computed(() => (props.limit > 0 ? props.used / props.limit : 0))
const over = computed(() => ratio.value > 1)
const width = computed(() => `${Math.min(100, Math.max(0, ratio.value * 100)).toFixed(1)}%`)

/** 三档配色: 安全(<60%) / 接近上限(<90%) / 超限 */
const tone = computed(() => {
  if (over.value) return { bar: '#d97878', color: '#c25f5f', hint: '#b95555' }
  if (ratio.value >= 0.9) return { bar: '#e0a75c', color: '#b8832f', hint: '#b8832f' }
  if (ratio.value >= 0.6) return { bar: '#c9bd6e', color: '#9a8f3f', hint: '#9a8f3f' }
  return { bar: '#8fb59a', color: '#5c8a6c', hint: '#7f9a88' }
})

const ariaLabel = computed(
  () =>
    `${props.label || '输入'}已用 ${usedText.value} ${unitText.value}` +
    (props.limit > 0 ? `, 上限 ${limitText.value} ${unitText.value}` : '')
)
</script>
