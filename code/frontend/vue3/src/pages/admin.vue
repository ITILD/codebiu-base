<template>
  <div p-4 md:p-6>
    <!-- 欢迎区: 时段问候 + 刷新 -->
    <div mb-6 flex items-center justify-between flex-wrap gap-4>
      <div>
        <h1 text-2xl font-bold text-note>{{ $t('hello_fmt', { g: $t(greeting), name: displayName }) }}</h1>
        <p text-sm text-note-sub mt-1>{{ $t('admin_welcome') }}</p>
      </div>
      <el-button :icon="Refresh" type="primary" @click="loadStatus">{{ $t('admin_refresh') }}</el-button>
    </div>

    <!-- 服务器状态统计卡(真实数据: getStatusCache 60s 缓存接口) -->
    <div grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6>
      <div
        v-for="card in statCards"
        :key="card.label"
        bg-note-card rounded-note-md p-5 shadow-note
      >
        <div flex items-center justify-between>
          <div min-w-0>
            <p text-sm text-note-sub>{{ card.label }}</p>
            <p text-2xl font-bold mt-2 text-note-green class="tabular-nums">{{ card.value }}</p>
            <p text-xs text-note-sub mt-1 truncate>{{ card.sub }}</p>
          </div>
          <div w-11 h-11 rounded-full bg-note-tint center shrink-0>
            <el-icon :size="24" text-note-green><component :is="card.icon" /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <!-- 快捷入口 -->
    <div mb-6>
      <h3 text-lg font-semibold text-note mb-4>{{ $t('admin_shortcuts') }}</h3>
      <div grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3>
        <RouterLink
          v-for="shortcut in shortcuts"
          :key="shortcut.path"
          :to="shortcut.path"
          flex flex-col items-center p-4 rounded-note-md bg-note-tint
          note-transition hover:-translate-y-1 hover:shadow-note hover:bg-note-card
        >
          <el-icon :size="28" mb-2 text-note-green>
            <component :is="shortcut.icon" />
          </el-icon>
          <span text-sm text-note>{{ shortcut.title }}</span>
        </RouterLink>
      </div>
    </div>

    <div grid grid-cols-1 lg:grid-cols-2 gap-4>
      <!-- 最近访问(localStorage 采集, 与主页共用) -->
      <div bg-note-card rounded-note-md p-5 shadow-note>
        <h3 font-semibold text-note mb-3>{{ $t('home_recent') }}</h3>
        <template v-if="recentPages.length">
          <RouterLink
            v-for="item in recentPages"
            :key="item.path"
            :to="item.path"
            flex items-center justify-between p-2 rounded-note-sm hover:bg-note-tint transition-colors
          >
            <div flex items-center gap-2 min-w-0>
              <el-icon text-note-sub><Clock /></el-icon>
              <span text-sm text-note truncate>{{ item.title }}</span>
            </div>
            <el-icon text-note-sub><ArrowRight /></el-icon>
          </RouterLink>
        </template>
        <p v-else text-sm text-note-sub>{{ $t('admin_no_recent') }}</p>
      </div>

      <!-- 系统信息 -->
      <div bg-note-card rounded-note-md p-5 shadow-note>
        <h3 font-semibold text-note mb-3>{{ $t('admin_sysinfo') }}</h3>
        <el-descriptions :column="1" border>
          <el-descriptions-item :label="$t('admin_sysver')">v1.0.0</el-descriptions-item>
          <el-descriptions-item :label="$t('admin_env')">{{ envText }}</el-descriptions-item>
          <el-descriptions-item :label="$t('admin_theme_mode')">{{ sysSettingStore.sysStyle.theme.isDark ? $t('dark') : $t('light') }}</el-descriptions-item>
          <el-descriptions-item :label="$t('admin_screen')">{{ screenLabel }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { markRaw, ref, computed, onMounted, onUnmounted } from 'vue'
import {
  Refresh, Cpu, Coin, Filter, Connection, Clock, ArrowRight,
} from '@element-plus/icons-vue'
import type { Component } from 'vue'
import { SysSettingStore } from '@/common/stores/sys'
import { useResponsive } from '@/common/composables/useResponsive'
import { useAuthStore } from '@/common/stores/auth'
import { useVisibleMenu } from '@/app/composables/useMenu'
import { useRecentPages } from '@/app/composables/useRecentPages'
import { getStatusCache } from '@/modules/main/api/status'
import type { HardwareStatus, NetworkStatus } from '@/modules/main/types/status'
// 系统三语(中/英/日): 脚本侧经 i18n.global.t 取词, 模板用 $t
import { i18n } from '@/common/i18n/language'

const sysSettingStore = SysSettingStore()
// 响应式断点: 屏幕档位描述用
const { isMd, isLg } = useResponsive()
const { t } = i18n.global
const authStore = useAuthStore()
const { recentPages } = useRecentPages()
const { visibleMenuItems } = useVisibleMenu()

const displayName = computed(() => authStore.authState.user.nickname || authStore.authState.user.username || '管理员')

/** 按时段返回问候语 i18n key(展示时经 $t 翻译) */
function greetingByHour(): string {
  const h = new Date().getHours()
  if (h < 6) return 'g_night'
  if (h < 12) return 'g_morning'
  if (h < 14) return 'g_noon'
  if (h < 18) return 'g_afternoon'
  return 'g_evening'
}
const greeting = ref(greetingByHour())

const envText = computed(() =>
  import.meta.env.MODE === 'development' ? t('env_dev') : t('env_prod')
)

/** 屏幕档位描述(三档断点) */
const screenLabel = computed(() => {
  if (isLg.value) return t('screen_desktop')
  if (isMd.value) return t('screen_tablet')
  return t('screen_phone')
})

// ===== 服务器状态(真实数据) =====
const hardware = ref<HardwareStatus | null>(null)
const network = ref<NetworkStatus[] | null>(null)

/** 统计卡: hardware 为 null 时显示 '-'(标签走 i18n, 语言切换即时刷新) */
const statCards = computed<{ label: string; value: string; sub: string; icon: Component }[]>(() => {
  const hw = hardware.value
  return [
    {
      label: t('admin_cpu'),
      value: hw ? `${hw.cpu.percent}%` : '-',
      sub: hw ? t('admin_cores_threads', { c: hw.cpu.cores, t: hw.cpu.threads }) : t('admin_no_data'),
      icon: markRaw(Cpu),
    },
    {
      label: t('admin_memory'),
      value: hw ? `${hw.memory.percent}%` : '-',
      sub: hw ? `${hw.memory.used} / ${hw.memory.total} GB` : t('admin_no_data'),
      icon: markRaw(Coin),
    },
    {
      label: t('admin_disk'),
      value: hw ? `${hw.disk.percent}%` : '-',
      sub: hw ? `${hw.disk.used} / ${hw.disk.total} GB` : t('admin_no_data'),
      icon: markRaw(Filter),
    },
    {
      label: t('admin_network'),
      value: network.value
        ? `${network.value.filter((n) => n.connect_success).length}/${network.value.length}`
        : '-',
      sub: t('admin_net_sub'),
      icon: markRaw(Connection),
    },
  ]
})

/** 拉取服务器状态(60s 缓存接口, 失败静默保持 '-') */
async function loadStatus() {
  try {
    const res = await getStatusCache()
    hardware.value = res?.hardware ?? null
    network.value = res?.network ?? null
  } catch {
    // 静默降级: 卡片显示 '-'
  }
}

// ===== 快捷入口: 从后台菜单树按路径挑选(自动带权限过滤, 未授权自动隐藏), 图标取父分组 =====
const SHORTCUT_PATHS = [
  '/authorization/user',
  '/ai/chat',
  '/file',
  '/monitor/server_status',
] as const

const shortcuts = computed(() => {
  // 展平菜单树并携带所属分组图标(显式标注避免分支类型不兼容)
  type FlatItem = { index: string; title: string; icon?: Component }
  const flatten: FlatItem[] = visibleMenuItems.value.flatMap((g): FlatItem[] =>
    g.children?.length
      ? g.children.map((c) => ({ index: c.index, title: c.title, icon: g.icon }))
      : [{ index: g.index, title: g.title, icon: g.icon }]
  )
  return SHORTCUT_PATHS.map((path) => flatten.find((m) => m.index === path))
    .filter((m): m is FlatItem => Boolean(m))
    .map((m) => ({ path: m.index, title: m.title, icon: m.icon }))
})

// 60s 自动刷新(与后端缓存周期对齐), 离开页面清理
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  loadStatus()
  timer = setInterval(loadStatus, 60_000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>
