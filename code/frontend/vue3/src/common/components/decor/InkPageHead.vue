<template>
  <!-- 后台页头(紧凑版): 标题 + 描述同行, 右侧操作区; 去掉大面积晕染与笔触,
       让首屏更快进入数据本身(对齐 SaaS 后台的紧凑信息密度) -->
  <header relative mb-3>
    <div relative flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5>
      <div min-w-0 flex flex-wrap items-baseline gap-x-3 gap-y-1>
        <h1 flex items-center gap-2 font-serif text-lg font-semibold text-note leading-tight>
          {{ title }}
          <span v-if="seal" class="note-seal page-head-seal" :title="sealTitle || title">{{ seal }}</span>
        </h1>
        <p v-if="sub || $slots.sub" min-w-0 text-xs text-note-sub leading-relaxed class="truncate">
          <slot name="sub">{{ sub }}</slot>
        </p>
      </div>

      <!-- 右侧操作区(开关/按钮/链接等) -->
      <div v-if="$slots.actions" flex flex-wrap items-center gap-2>
        <slot name="actions" />
      </div>
    </div>

    <!-- 细分隔线: 两端淡出, 比枯笔笔触更安静 -->
    <div class="note-line-fade" mt-2 aria-hidden="true" />
  </header>
</template>

<script setup lang="ts">
// 页面标题头(后台紧凑版): 统一 CRUD/工具页的页头观感
// 亮暗自适应: 全部取值来自 base.css 的 --note-* 变量, 无硬编码色
withDefaults(defineProps<{
  /** 页面标题 */
  title: string
  /** 标题下描述文案(可用 #sub 插槽替代) */
  sub?: string
  /** 朱砂闲章单字(如 憩/员/枝), 不传则不显示 */
  seal?: string
  /** 闲章 title 提示, 默认用页面标题 */
  sealTitle?: string
}>(), {})
</script>

<style scoped>
/* 缩小闲章: 页头尺度下不抢标题 */
.page-head-seal {
    width: 1.5rem;
    height: 1.5rem;
    font-size: 0.8rem;
    border-radius: 4px;
    transform: rotate(-3deg);
}
</style>
