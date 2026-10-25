<template>
  <!-- 中式水墨主题展示页 -->
  <InkShowcase :theme="ink" />
</template>

<script setup lang="ts">
// 中式水墨主题子页面: 国画手卷式布局, 复用首页水墨小池作引首
import InkShowcase from '../../components/playground/InkShowcase.vue'
import { playgroundThemes } from '../../components/playground/themes'

const ink = playgroundThemes.find((t) => t.key === 'ink')!
</script>
