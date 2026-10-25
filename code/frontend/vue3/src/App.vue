<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useAuthStore } from '@/common/stores/auth'
import { useRecentPages } from '@/app/composables/useRecentPages'
import { findMenuTrail } from '@/app/config/menu'
import { http_base_server } from '@/common/api/http'
// 侧边栏仅后台路由渲染: 异步组件将其从首屏入口分包剥离, 进入后台管理时才加载
const SysSidebar = defineAsyncComponent(() => import('@/app/components/layout/SysSidebar.vue'))
// 语言切换: EP 组件内建文案(pagination/date-picker 等)随界面语言同步
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import jaJp from 'element-plus/es/locale/lang/ja'
import enUs from 'element-plus/es/locale/lang/en'
import type { Language } from 'element-plus/es/locale'
import { applyI18nOverrides, currentLanguage } from '@/common/i18n/language'

// Element Plus 语言包映射(与 common/i18n 语言码对齐)
const EP_LOCALES: Record<string, Language> = { zh: zhCn, ja: jaJp, en: enUs }
const epLocale = computed(() => EP_LOCALES[currentLanguage.value] ?? zhCn)

const route = useRoute()
const router = useRouter()
// 后台管理页面才显示左侧模块列表, 首页等为纯展示布局(页首+内容+页脚)
// admin 标记由 vite.config.ts 的 extendRoute 写入路由 meta;
// standalone 页面(如账户设置)虽属后台路由, 但页面自带导航, 不渲染侧边栏
const isAdmin = computed(() => Boolean(route.meta.admin && !route.meta.standalone))
// 全屏页面(如三维地球): 锁定文档滚动(滚轮留给场景缩放), 页脚隐藏
const isFullpage = computed(() => Boolean(route.meta.fullpage))

// 最近访问采集: 记录前台应用(app)与后台(admin)路由, 标题取菜单树末级
const { pushRecent } = useRecentPages()
watch(
  () => route.path,
  (path) => {
    if (!route.meta.admin && !route.meta.app) return
    // 兼容 es2020 lib: 用索引取末级而非 Array.prototype.at
    const trail = findMenuTrail(path)
    const title = trail.length > 0 ? trail[trail.length - 1].title : path
    pushRecent(path, title)
  }
)

// 浏览器标签标题: 跟随当前菜单末级(未收录路由回落应用名), 便于多标签页辨识
const APP_TITLE = import.meta.env.VITE_GLOB_APP_TITLE
watch(
  () => route.path,
  (path) => {
    const trail = findMenuTrail(path)
    const menuTitle = trail.length > 0 ? trail[trail.length - 1].title : ''
    document.title = menuTitle ? `${menuTitle} · ${APP_TITLE}` : APP_TITLE
  },
  { immediate: true },
)

// 应用挂载时为已登录用户刷新权限(修复旧会话持久化的空/过期权限导致菜单被隐藏)
const authStore = useAuthStore()
onMounted(() => {
  if (!authStore.authState.user.id) return
  authStore.fetchPermissions()
  // 会话恢复时套用该用户保存的样式配置(主题), 与登录后切换保持一致
  authStore.applyUserTheme()
})

// 后台维护的词条覆盖: 启动即合并进语言包(未登录/无权限时静默跳过, 不阻塞首屏)
async function loadI18nOverrides() {
  try {
    const rows = await http_base_server.get<Array<{ key: string; zh?: string | null; ja?: string | null; en?: string | null }>>(
      '/i18n/overrides',
    )
    const overrides: Record<string, string[]> = {}
    for (const row of rows) overrides[row.key] = [row.zh ?? '', row.ja ?? '', row.en ?? '']
    applyI18nOverrides(overrides)
  } catch {
    // 未登录或接口未就绪: 使用内置词条即可
  }
}

// 路由懒加载占位: 首次解析页面组件耗时超过阈值才显示骨架, 避免瞬间闪烁
const routeLoading = ref(false)
let routeLoadingTimer: ReturnType<typeof setTimeout> | null = null

/** 结束加载态并清理定时器 */
function stopRouteLoading() {
  if (routeLoadingTimer) {
    clearTimeout(routeLoadingTimer)
    routeLoadingTimer = null
  }
  routeLoading.value = false
}

const removeBeforeEach = router.beforeEach(() => {
  if (routeLoadingTimer) clearTimeout(routeLoadingTimer)
  routeLoadingTimer = setTimeout(() => { routeLoading.value = true }, 180)
})
const removeAfterEach = router.afterEach(() => stopRouteLoading())
const removeOnError = router.onError(() => stopRouteLoading())

// 词条覆盖跟随登录态加载: 未登录不请求(避免无谓 401), 登录/切换账号后自动重新合并
watch(
  () => authStore.authState.user.id,
  (userId) => { if (userId) loadI18nOverrides() },
  { immediate: true },
)

onUnmounted(() => {
  removeBeforeEach()
  removeAfterEach()
  removeOnError()
  stopRouteLoading()
})
</script>

<template>
  <!-- EP ConfigProvider: 组件内建文案随语言切换; 整体: 吸顶导航 +
       (后台: 粘性侧边栏 + 主内容) + 页脚(文档末尾)
       注意: 不包 Suspense —— 无组件使用顶层 await, 且 Suspense 会与
       路由 Transition(out-in) 冲突导致切页后视图空白 -->
  <el-config-provider :locale="epLocale">
    <div class="flex flex-col bg-note-paper" :class="isFullpage ? 'h-screen overflow-hidden' : 'min-h-screen'">
    <!-- 顶部栏(吸顶+毛玻璃): 滚动时钉在视口顶部
         注意: bg-note-glass 含方括号任意值, 必须写进 class 属性(attributify 陷阱)
         高度保持 h-14 md:h-16 不变 —— h-app/max-h-app 公式与侧边栏 top-16 依赖它 -->
    <SysHeader
      class="note-edge-b sticky top-0 z-20 h-14 md:h-16 shrink-0 bg-note-glass backdrop-blur-md"
    />

    <div flex flex-1 items-start>
      <!-- 左侧模块列表(仅后台路由): 钉在吸顶导航下方, 菜单内部滚动 -->
      <SysSidebar v-if="isAdmin" />

      <!-- 主内容区: 文档流自然滚动
           注意: 此处不要用 Transition 包裹路由组件(路由切换过渡已移除) ——
           与路由懒加载组件组合存在组件更新时 parentNode(null) 导致
           整页空白的 bug(out-in 与交叉淡入两种模式均已踩坑),
           故直接渲染 RouterView 保证稳定;
           keep-alive 仅缓存重状态对话页(RagConversation, 按 include
           组件名匹配, 页面内 defineOptions 声明): 切回免整页重建与数据重拉,
           流式输出切走不中断; 其余页面不缓存避免数据陈旧 -->
      <main flex-1 min-w-0 w-full relative>
        <!-- 全局错误边界: 页面级异常回退为可重试卡片, 避免整站白屏 -->
        <AppErrorBoundary>
          <RouterView v-slot="{ Component }">
            <keep-alive :include="['RagConversation']">
              <component :is="Component" />
            </keep-alive>
          </RouterView>
        </AppErrorBoundary>
        <!-- 路由懒加载占位: 覆盖旧页面, 加载完成后自然消失 -->
        <div v-if="routeLoading" class="absolute inset-0 z-10 bg-note-paper px-4 py-6 md:px-6" aria-busy="true">
          <RouteSkeleton variant="paragraph" />
        </div>
      </main>
    </div>

    <!-- 页脚: 位于文档末尾, 随内容增长(全屏页面隐藏, 避免产生文档滚动) -->
    <SysFooter v-if="!isFullpage" w-full shrink-0 />

    <!-- 悬浮 AI 助手: 右下/左下悬浮按钮 + 异步弹开面板(后台「AI 服务 · AI 助手配置」控制) -->
    <AssistantFloat />
    <!-- 悬浮工具(可拖动): 全屏/截图/隐藏; 显隐由 设置-外观 持久化控制 -->
    <FloatTools />
    </div>
  </el-config-provider>
</template>
