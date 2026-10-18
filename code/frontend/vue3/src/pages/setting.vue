<template>
  <div p-4 md:p-6>
    <h1 text-2xl font-bold text-note mb-6>设置</h1>

    <div class="flex flex-col md:flex-row gap-4">
      <!-- 左侧导航(移动端横向滚动, 桌面端垂直): tab 语义便于读屏与键盘切换 -->
      <nav
        role="tablist"
        aria-label="设置分组"
        class="flex md:flex-col gap-1 md:w-48 shrink-0 bg-note-card rounded-lg shadow-note p-2 overflow-x-auto md:overflow-visible">
        <button v-for="tab in tabs" :key="tab.key"
          type="button" role="tab" :aria-selected="active === tab.key"
          class="flex items-center gap-2 rounded px-3 py-2 text-sm whitespace-nowrap transition-colors cursor-pointer"
          :class="active === tab.key
            ? 'bg-note-green/10 text-note-green font-medium'
            : 'text-note-sub hover:bg-note-tint'"
          @click="active = tab.key">
          <el-icon aria-hidden="true"><component :is="tab.icon" /></el-icon>
          {{ $t(`tab_${tab.key}`) }}
        </button>
      </nav>

      <!-- 右侧内容面板: 直接渲染动态组件 —— 不要用 Transition(out-in) 包裹,
           与动态组件组合存在 parentNode(null) 空白 bug(见 App.vue 路由层同款踩坑),
           表现为切换子页后面板无内容 -->
      <section role="tabpanel" class="flex-1 min-w-0 bg-note-card rounded-lg shadow-note p-4 md:p-6">
        <component :is="activeComponent" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { markRaw } from 'vue'
import { User, Lock, Brush, Key, Cpu } from '@element-plus/icons-vue'
import SettingProfile from '@/app/components/setting/SettingProfile.vue'
import SettingPassword from '@/app/components/setting/SettingPassword.vue'
import SettingBase from '@/app/components/setting/SettingBase.vue'
import SettingPermission from '@/app/components/setting/SettingPermission.vue'
import SettingModel from '@/app/components/setting/SettingModel.vue'

/** 设置分组: 个人信息(自助修改) + 模型绑定 + 系统样式
 *  标签文案按 key 约定走 i18n: tab_profile/tab_password/tab_model/tab_appearance/tab_permission */
const tabs = [
  { key: 'profile', icon: markRaw(User), component: SettingProfile },
  { key: 'password', icon: markRaw(Lock), component: SettingPassword },
  { key: 'model', icon: markRaw(Cpu), component: SettingModel },
  { key: 'appearance', icon: markRaw(Brush), component: SettingBase },
  { key: 'permission', icon: markRaw(Key), component: SettingPermission },
] as const

type TabKey = (typeof tabs)[number]['key']
const active = ref<TabKey>('profile')
const activeComponent = computed(() => tabs.find((t) => t.key === active.value)?.component)
</script>
