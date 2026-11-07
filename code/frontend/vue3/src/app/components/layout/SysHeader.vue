<template>
  <!-- 网站页首: Logo/汉堡/面包屑(左) + 主题切换/登录/头像(右)
       吸顶与毛玻璃样式由 App.vue 传入(sticky + bg-note-glass), 此处只管内容布局 -->
  <header v-if="sysStyle.headFootShow">
    <div flex items-center justify-between h-full min-w-0>
      <!-- 左侧: 移动端汉堡(仅后台路由, 打开模块列表抽屉) + Logo + 面包屑 -->
      <div flex items-center min-w-0 flex-1>
        <button
          v-if="isAdmin && !isMd"
          ml-3
          rounded-full
          hover:bg-note-tint
          p-2
          min-w-11
          min-h-11
          flex
          items-center
          justify-center
          shrink-0
          type="button"
          aria-label="打开侧边菜单"
          @click="sysSettingStore.sysStyle.isSidebarDrawerOpen = true"
        >
          <el-icon :size="22" text-note>
            <Menu />
          </el-icon>
        </button>

        <router-link to="/" flex items-center ml-3 sm:ml-4 md:ml-8 shrink-0 min-w-0 :aria-label="TITLE">
          <!-- 双图叠放 + 透明度过渡: 切换主题时 Logo 交叉淡入淡出, 不再整张重载闪一下 -->
          <span class="logo-mark" aria-hidden="true">
            <img :src="logoLight" alt="" class="logo-img" :class="{ 'is-current': !sysStyle.theme.isDark }" />
            <img :src="logoDark" alt="" class="logo-img" :class="{ 'is-current': sysStyle.theme.isDark }" />
          </span>
          <!-- 手机档(<640px)只留 Logo: 品牌名 + 汉堡 + 右侧四个控件在 375px 会溢出 -->
          <span
            v-ellipsis
            hidden
            sm:inline
            text-lg
            md:text-xl
            font-semibold
            whitespace-nowrap
            truncate
            text-note
            class="max-w-[34vw] md:max-w-none"
          >
            {{ TITLE }}
          </span>
        </router-link>

        <!-- 面包屑(仅后台路由, 平板及以上显示; 手机由抽屉菜单承担定位) -->
        <SysBreadcrumb class="ml-6 flex-1 min-w-0" />
      </div>

      <!-- 右侧: 版本更新按钮 + 语言切换 + 主题切换 + 登录/用户
           手机档收紧间距与页边距, 避免多控件时溢出 -->
      <div flex items-center mr-3 md:mr-8 gap-1.5 md:gap-3 shrink-0>
        <!-- 新版本发布提示(按钮而非弹窗, 点击刷新加载新资源) -->
        <VersionRefresh />
        <!-- 语言切换(中/英/日; 平板及以上显示, 手机经 设置-外观 调整) -->
        <el-dropdown v-if="isMd" trigger="click" @command="changeLanguage">
          <button
            type="button"
            aria-label="切换语言"
            flex
            items-center
            rounded
            h-8
            px-2
            text-sm
            text-note
            hover:bg-note-tint
            note-transition
          >
            {{ currentLanguageLabel }}
            <el-icon class="ml-1" :size="12"><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in languageOptions"
                :key="opt.value"
                :command="opt.value"
                :disabled="opt.value === currentLanguage"
              >
                {{ opt.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- 主题切换: 受控模式 + 圆形揭幕过渡(见 handleThemeToggle) -->
        <span class="theme-switch-wrap" h-8 flex items-center data-theme-toggle>
          <el-switch
            :model-value="sysStyle.theme.isDark"
            aria-label="切换深色模式"
            @change="handleThemeToggle"
          />
        </span>
        <!-- 登录/用户 -->
        <template v-if="authState.user.id">
          <NotificationBell />
          <UserControl />
        </template>
        <template v-else>
          <button
            flex
            items-center
            justify-center
            rounded
            px-3
            py-1.5
            text-note
            hover:bg-note-tint
            transition-colors
            @click="showLoginDialog = true"
          >
            <!-- 登录 -->
            {{ $t('sign_in') }}
          </button>
          <!-- 注册按钮 小屏幕隐藏(淡绿软底替代描边) -->
          <button
            max-lg:hidden
            flex
            items-center
            justify-center
            rounded
            px-3
            py-1.5
            type="button"
            bg-note-tint
            text-note
            hover:shadow-note
            note-transition
            @click="showRegisterDialog = true"
          >
            {{ $t('sign_up') }}
          </button>

          <!-- 登录弹窗(异步组件: 门闩激活后挂载, 见 script 内注释) -->
          <LoginDialog
            v-if="authDialogsActivated"
            v-model="showLoginDialog"
            @login="handleLogin"
            @register="showRegisterDialog = true; showLoginDialog = false"
          />

          <!-- 注册弹窗(异步组件) -->
          <RegisterDialog
            v-if="authDialogsActivated"
            v-model="showRegisterDialog"
            @register-success="handleRegisterSuccess"
            @back-to-login="showRegisterDialog = false; showLoginDialog = true"
          />
        </template>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
// 样式控制
import { SysSettingStore } from '@/common/stores/sys'
import { useResponsive } from '@/common/composables/useResponsive'
import { Menu, ArrowDown } from '@element-plus/icons-vue'
// 语言切换(中/英/日)
import { languageOptions, currentLanguage, changeLanguage } from '@/common/i18n/language'
// 面包屑(应用壳布局组件)
import SysBreadcrumb from './SysBreadcrumb.vue'
// 登录/注册/用户控件属于 authorization 模块的登录认证功能(应用壳只做组装)
// 弹窗改异步组件 + 激活门闩(authDialogsActivated): 首次打开才拉取对应分包,
// 登录表单/验证码倒计时等逻辑不再随首屏入口下载; 打开过一次后保持挂载,
// 关闭动画与再次打开不受影响
const LoginDialog = defineAsyncComponent(() => import('@/modules/authorization/components/LoginDialog.vue'))
const RegisterDialog = defineAsyncComponent(() => import('@/modules/authorization/components/RegisterDialog.vue'))
import UserControl from '@/modules/authorization/components/UserControl.vue'
// 通知铃铛属于 contact 模块的通知中心功能(REQ-011, 登录态显示)
import NotificationBell from '@/modules/contact/components/NotificationBell.vue'
import { useAuthStore } from '@/common/stores/auth'
import type { AuthResponse } from '@/modules/authorization/types/auth'
// Logo 按明暗主题切换: 亮色用浅底版, 暗色用深青底版(避免暗色下发白刺眼)
import logoLight from '@/assets/img/ion/sy_w.svg'
import logoDark from '@/assets/img/ion/sy_d.svg'
const authStore = useAuthStore()
const authState = authStore.authState
const sysSettingStore = SysSettingStore()
const sysStyle = sysSettingStore.sysStyle
// 响应式断点: 汉堡按钮仅在 md 以下显示
const { isMd } = useResponsive()
// 当前语言全称(切换器触发钮展示, 以各自语言书写)
const currentLanguageLabel = computed(
  () => languageOptions.find((o) => o.value === currentLanguage.value)?.label ?? '简体中文'
)
const showLoginDialog = ref(false)
const showRegisterDialog = ref(false)
// 弹窗激活门闩: 任一弹窗首次打开时置真, 之后保持挂载(见顶部注释)
const authDialogsActivated = ref(false)
watch([showLoginDialog, showRegisterDialog], ([login, register]) => {
  if (login || register) authDialogsActivated.value = true
})
const TITLE = ref(import.meta.env.VITE_GLOB_APP_TITLE)

const route = useRoute()
const router = useRouter()
// 仅后台路由显示汉堡(打开侧边栏抽屉), admin 标记见 vite.config.ts 的 extendRoute;
// bare=1 为首页入口卡进入的单页模式, 不渲染侧边栏, 汉堡同步隐藏
const isAdmin = computed(() =>
  Boolean(route.meta.admin && !route.meta.standalone && String(route.query.bare ?? '') !== '1')
)

// 未登录被拦截回首页时自动弹出登录框
watch(
  () => route.query.login,
  (v) => {
    if (v === '1') showLoginDialog.value = true
  },
  { immediate: true },
)

// 未登录调用需登录接口(首页公开功能 401)时, http 层广播事件弹出登录框(见 common/api/http.ts)
const onPromptLogin = () => {
  showLoginDialog.value = true
}
onMounted(() => window.addEventListener('app:prompt-login', onPromptLogin))
onUnmounted(() => window.removeEventListener('app:prompt-login', onPromptLogin))

// 处理登录
const handleLogin = (authResponse: AuthResponse) => {
  authStore.setAuthState(authResponse)
  // 登录后拉取角色与权限码(侧边栏菜单/按钮权限的过滤依据)
  authStore.fetchPermissions()
  // 套用该用户保存的样式配置(主题), 换账号登录时同步切换
  authStore.applyUserTheme()
  // 清理登录引导参数, 避免再次进入首页重复弹出登录框
  if (route.query.login) {
    const { login: _login, ...rest } = route.query
    router.replace({ query: rest })
  }
}

// 处理注册成功
const handleRegisterSuccess = (authResponse: AuthResponse) => {
  // 注册成功后自动登录
  authStore.setAuthState(authResponse)
  // 拉取新账户的角色与权限码
  authStore.fetchPermissions()
  // 套用该账户保存的样式配置(新账户默认跟随系统)
  authStore.applyUserTheme()
}

// 顶栏黑白开关: 二态切换后套用主题并同步到后端用户配置。
// 支持 View Transitions 的浏览器从开关位置做圆形揭幕, 避免整页硬切导致刺眼闪屏;
// 不支持或用户偏好减少动效时, 直接切换。
const handleThemeToggle = (value: string | number | boolean) => {
  const theme = value ? 'dark' : 'light'
  const apply = () => {
    sysSettingStore.applyThemeValue(theme)
    authStore.saveUserTheme(theme)
  }


  const ViewTransitionDoc = document as Document & {
    startViewTransition?: (cb: () => Promise<void>) => { finished: Promise<void> }
  }
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!ViewTransitionDoc.startViewTransition || reduceMotion) {
    apply()
    return
  }

  // 揭幕圆心取主题开关中心, 半径覆盖到最远屏角
  const root = document.documentElement
  const trigger = document.querySelector<HTMLElement>('[data-theme-toggle]')
  const rect = trigger?.getBoundingClientRect()
  const x = rect ? rect.left + rect.width / 2 : window.innerWidth - 64
  const y = rect ? rect.top + rect.height / 2 : 28
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y)) + 24
  root.style.setProperty('--note-reveal-x', `${x}px`)
  root.style.setProperty('--note-reveal-y', `${y}px`)
  root.style.setProperty('--note-reveal-r', `${radius}px`)

  const cleanup = () => {
    root.style.removeProperty('--note-reveal-x')
    root.style.removeProperty('--note-reveal-y')
    root.style.removeProperty('--note-reveal-r')
  }

  try {
    const transition = ViewTransitionDoc.startViewTransition(() => {
      apply()
      // useDark 的 html.dark 写入在下一微任务才生效; 这里同步落类,
      // 保证浏览器截取"新快照"时已经是目标主题, 避免 DOM 更新超时/回退闪一下
      document.documentElement.classList.toggle('dark', theme === 'dark')
    })
    transition.finished.finally(cleanup)
  } catch {
    cleanup()
    apply()
  }
}
</script>

<style scoped>
/* Logo 交叉淡化容器: 两版 Logo 同时挂载, 只切透明度, 不触发图片重新加载 */
.logo-mark {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-right: 12px;
  flex-shrink: 0;
}

.logo-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
  transition: opacity 0.18s ease-out;
}

.logo-img.is-current {
  opacity: 1;
}
</style>
