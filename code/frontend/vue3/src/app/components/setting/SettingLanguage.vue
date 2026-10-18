<template>
  <!-- 语言选择: 三语(简体中文/日本語/English), 切换立即生效并持久化 -->
  <div flex items-center gap-2 p-1>
    <span w-20 shrink-0>{{ $t('language') }}</span>
    <el-select :model-value="currentLanguage" @change="changeLanguage">
      <el-option
        v-for="item in languageOptions"
        :key="item.value"
        :label="item.label"
        :value="item.value"
      />
    </el-select>
  </div>
</template>

<script setup lang="ts">
import { languageOptions, currentLanguage, changeLanguage } from '@/common/i18n/language'
</script>
