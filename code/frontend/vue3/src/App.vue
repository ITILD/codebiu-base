<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useAuthStore } from '@/common/stores/auth'
import { useRecentPages } from '@/app/composables/useRecentPages'
import { findMenuTrail } from '@/app/config/menu'
// 侧边栏仅后台路由渲染: 异步组件将其从首屏入口分包剥离, 进入后台管理时才加载
const SysSidebar = defineAsyncComponent(() => import('@/app/components/layout/SysSidebar.vue'))
// 语言切换: EP 组件内建文案(pagination/date-picker 等)随界面语言同步
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import jaJp from 'element-plus/es/locale/lang/ja'
import enUs from 'element-plus/es/locale/lang/en'
import type { Language } from 'element-plus/es/locale'
import { currentLanguage } from '@/common/i18n/language'

// Element Plus 语言包映射(与 common/i18n 语言码对齐)
const EP_LOCALES: Record<string, Language> = { zh: zhCn, ja: jaJp, en: enUs }
const epLocale = computed(() => EP_LOCALES[currentLanguage.value] ?? zhCn)

const route = useRoute()
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

// 应用挂载时为已登录用户刷新权限(修复旧会话持久化的空/过期权限导致菜单被隐藏)
const authStore = useAuthStore()
onMounted(() => {
  if (authStore.authState.user.id) authStore.fetchPermissions()
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
           keep-alive 仅缓存重状态对话页(RagConversation/AiChat, 按 include
           组件名匹配, 页面内 defineOptions 声明): 切回免整页重建与数据重拉,
           流式输出切走不中断; 其余页面不缓存避免数据陈旧 -->
      <main flex-1 min-w-0 w-full>
        <RouterView v-slot="{ Component }">
          <keep-alive :include="['RagConversation', 'AiChat']">
            <component :is="Component" />
          </keep-alive>
        </RouterView>
      </main>
    </div>

    <!-- 页脚: 位于文档末尾, 随内容增长(全屏页面隐藏, 避免产生文档滚动) -->
    <SysFooter v-if="!isFullpage" w-full shrink-0 />

    <!-- 悬浮工具(可拖动): 全屏/截图/隐藏; 显隐由 设置-外观 持久化控制 -->
    <FloatTools />
    </div>
  </el-config-provider>
</template>
