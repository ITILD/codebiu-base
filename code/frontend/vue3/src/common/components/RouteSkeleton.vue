<script setup lang="ts">
/**
 * 路由切换占位骨架: 按页面类型组合 NoteSkeleton, 高度随内容自适应父容器。
 * loading 说明仅对读屏可见, 骨架图形本身 aria-hidden。
 */
import NoteSkeleton from '@/common/components/NoteSkeleton.vue'
import { i18n } from '@/common/i18n/language'

interface Props {
  /** 页面骨架形态(默认表格) */
  variant?: 'post' | 'table' | 'stat' | 'list' | 'paragraph' | 'block' | 'admin'
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

    <!-- 后台 CRUD 页: 页头 + 搜索卡片 + 表格卡片, 按真实布局占位,
         页面渲染完成时骨架让位不产生结构跳变 -->
    <div v-else-if="props.variant === 'admin'" class="flex w-full min-w-0 flex-col gap-3">
      <div class="flex items-center gap-3">
        <div class="note-sk h-5 w-36" />
        <div class="note-sk h-3 w-24" />
      </div>
      <div class="page-card flex flex-wrap items-center gap-3 px-3 py-3">
        <div v-for="i in 3" :key="i" class="note-sk h-8 w-44 rounded-note-md" />
        <div class="ml-auto flex items-center gap-2">
          <div class="note-sk h-8 w-20 rounded-note-md" />
          <div class="note-sk h-8 w-24 rounded-note-md" />
        </div>
      </div>
      <div class="page-card min-w-0 px-3 pb-3 pt-2">
        <div class="flex items-center justify-between py-1">
          <div class="note-sk h-3 w-24" />
          <div class="note-sk h-7 w-28 rounded-note-md" />
        </div>
        <NoteSkeleton variant="table" :rows="6" />
      </div>
    </div>

    <!-- 其余形态: 单一骨架(表格行数取 6, 避免首屏过高) -->
    <NoteSkeleton
      v-else
      :variant="props.variant"
      :rows="props.variant === 'table' ? 6 : 5"
    />
  </div>
</template>
