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

        <router-link to="/" flex items-center ml-3 sm:ml-4 md:ml-8 shrink-0 min-w-0>
          <img :src="sysStyle.theme.isDark ? logoDark : logoLight" h-8 mr-3 alt="logo" />
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
            px-2
            py-1.5
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
        <!-- 主题切换 -->
        <el-switch
          v-model="sysSettingStore.sysStyle.theme.isDark"
          aria-label="切换深色模式"
          @change="handleThemeToggle"
        />
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
// 仅后台路由显示汉堡(打开侧边栏抽屉), admin 标记见 vite.config.ts 的 extendRoute
const isAdmin = computed(() => Boolean(route.meta.admin && !route.meta.standalone))

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

// 顶栏黑白开关: 二态切换后套用主题并同步到后端用户配置
const handleThemeToggle = (value: string | number | boolean) => {
  const theme = Boolean(value) ? 'dark' : 'light'
  sysSettingStore.applyThemeValue(theme)
  authStore.saveUserTheme(theme)
}
</script>
