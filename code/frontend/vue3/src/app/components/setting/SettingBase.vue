<template>
  <div p-2 flex flex-col gap-2>
    <!-- 黑白主题 -->
    <div flex items-center gap-2>
      <span w-20 shrink-0>{{ $t('theme') }}</span>
      <el-select
        v-model="sysSettingStore.sysStyle.theme.themeValue"
        :placeholder="$t('theme')"
        @change="handleThemeChange"
      >
        <el-option
          v-for="option in themeOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>
    </div>
    <!-- 语言选择 -->
    <SettingLanguage />
    <!-- 悬浮工具显隐: 隐藏页面右侧可拖动悬浮球(全屏/截图/隐藏入口) -->
    <div flex items-center gap-2>
      <span w-20 shrink-0>{{ $t('float_tools') }}</span>
      <el-switch v-model="showFloatTools" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { SysSettingStore } from '@/common/stores/sys'
import { useAuthStore } from '@/common/stores/auth'
import type { ThemeMode } from '@/common/types/theme'
import { i18n } from '@/common/i18n/language'
const sysSettingStore = SysSettingStore()
const authStore = useAuthStore()
// 悬浮工具开关(语义取反: 开关=显示, store 存"隐藏")
const showFloatTools = computed({
  get: () => !sysSettingStore.floatToolsHidden,
  set: (v) => (sysSettingStore.floatToolsHidden = !v)
})
/////////////////////////////////////////////////////////主题控制/////////////////////////////////////////////////////////
// 主题选择
const themeOptions = computed(() => [
  { value: 'light', label: i18n.global.t('light') },
  { value: 'dark', label: i18n.global.t('dark') },
  { value: 'auto', label: i18n.global.t('autoSys') }
])

// 切换主题: 立即套用并持久化本地, 登录用户同时同步到后端用户配置
const handleThemeChange = (value: ThemeMode) => {
  sysSettingStore.applyThemeValue(value)
  authStore.saveUserTheme(value)
}

/////////////////////////////////////////////////////////todo/////////////////////////////////////////////////////////
</script>
