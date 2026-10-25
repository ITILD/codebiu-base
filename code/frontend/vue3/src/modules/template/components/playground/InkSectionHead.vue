<template>
  <!-- 水墨区块小标题: 朱砂序号 + 手写体题名 + 右侧一句注 -->
  <div class="relative mb-2.5 flex items-baseline gap-2">
    <span class="ink-head__no">{{ no }}</span>
    <h3 class="font-hand text-lg tracking-[0.18em] text-[#2b332e]">{{ title }}</h3>
    <span class="ml-auto hidden text-[11px] tracking-[0.2em] text-[#8a918a] sm:block">{{ note }}</span>
  </div>
</template>

<script setup lang="ts">
// 水墨主题区块标题(仅供 InkShowcase 使用)
defineProps<{
  /** 序号(壹/貳/叁…), 以朱砂小印呈现 */
  no: string
  /** 题名 */
  title: string
  /** 右侧小注 */
  note?: string
}>()
</script>

<style scoped>
/* 朱砂序号: 空心小印, 不抢正文 */
.ink-head__no {
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border: 1px solid rgba(168, 70, 47, 0.7);
    border-radius: 2px;
    color: #a8462f;
    font-family: var(--note-font-hand);
    font-size: 11px;
    line-height: 1;
}
</style>
