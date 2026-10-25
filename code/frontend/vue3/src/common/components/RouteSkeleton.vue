<script setup lang="ts">
/**
 * 路由切换占位骨架: 按页面类型组合 NoteSkeleton, 高度随内容自适应父容器。
 * loading 说明仅对读屏可见, 骨架图形本身 aria-hidden。
 */
import NoteSkeleton from '@/common/components/NoteSkeleton.vue'
import { i18n } from '@/common/i18n/language'

interface Props {
  /** 页面骨架形态(默认表格) */
  variant?: 'post' | 'table' | 'stat' | 'list' | 'paragraph' | 'block'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'table',
})

const { t } = i18n.global
</script>

<template>
  <div class="w-full min-w-0" role="status" aria-live="polite">
    <span class="sr-only">{{ t('loading') }}</span>

    <!-- 概览型页面: 多列统计条 -->
    <div v-if="props.variant === 'stat'" class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <NoteSkeleton v-for="i in 4" :key="i" variant="stat" />
    </div>

    <!-- 文章/卡片列表: 两列卡片流 -->
    <div v-else-if="props.variant === 'post'" class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <NoteSkeleton v-for="i in 2" :key="i" variant="post" />
    </div>

    <!-- 其余形态: 单一骨架(表格行数取 6, 避免首屏过高) -->
    <NoteSkeleton
      v-else
      :variant="props.variant"
      :rows="props.variant === 'table' ? 6 : 5"
    />
  </div>
</template>
