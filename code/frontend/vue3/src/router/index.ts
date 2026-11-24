import { createRouter, createWebHistory } from 'vue-router'
/**
 * 自动路由
 * 原本routes更换
 * 路由规则 https://uvr.esm.is/guide/file-based-routing.html
 */
import { routes, handleHotUpdate } from "vue-router/auto-routes"
import { RouterStore } from '@/common/stores/router'
import { useAuthStore } from '@/common/stores/auth'
import { usePermission } from '@/common/composables/usePermission'
import { menuItems } from '@/app/config/menu'
import { ElMessage } from 'element-plus'

// 路由 meta 类型扩展(admin 由 vite.config.ts 的 extendRoute 统一标记:
// 首页与 404 为公开页, 其余业务页(含 rag/agent)均为后台路由)
declare module 'vue-router' {
  interface RouteMeta {
    /** 后台管理路由: 需登录访问(默认显示侧边栏; ?bare=1 时仅隐藏侧边栏) */
    admin?: boolean
    /** 独立页面: 属后台路由(需登录), 但不渲染左侧模块侧边栏(如账户设置) */
    standalone?: boolean
  }
}

// 菜单路径 -> 权限码映射(守卫据此拦截无权限页面的直链访问, 与侧边栏过滤同口径)
const menuPermByPath = new Map<string, string>()
for (const group of menuItems) {
  if (group.perm) menuPermByPath.set(group.index, group.perm)
  for (const leaf of group.children ?? []) {
    if (leaf.perm) menuPermByPath.set(leaf.index, leaf.perm)
  }
}

// 生成路由  注意nginx发布配置 添加跳转
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: routes,
  // 滚动记忆: 浏览器后退/前进恢复原位置; 锚点跳转交给 CSS scroll-padding-top 让出吸顶栏
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth', top: 72 }
    return { top: 0 }
  },
})

// 路由监听(返回值风格: vue-router 4.2+ 已弃用 next() 第三参数形态)
router.beforeEach((to) => {
  const routerStore = RouterStore()
  routerStore.setRouterPath(to.path)
  // 登录拦截: 后台功能页(含从首页入口卡进入的单页模式)均需登录
  const authStore = useAuthStore()
  if (to.meta.admin && !authStore.authState.user.id) {
    ElMessage.warning('请先登录后再访问')
    return { path: '/', query: { login: '1' } }
  }
  // 权限拦截: 菜单标注权限码的页面, 普通用户直输 URL 也无法绕过
  // (权限码未加载完成时放行, 由页面空态与后端接口鉴权兜底, 避免登录竞态误伤)
  const perm = menuPermByPath.get(to.path)
  if (perm && authStore.authState.user.id && authStore.permState.permissions.length > 0) {
    const { hasPerm } = usePermission()
    if (!hasPerm(perm)) {
      ElMessage.warning('暂无访问权限')
      return { path: '/' }
    }
  }
})

// 开发模式
if (import.meta.env.DEV) {
  console.log('开发模式')
  // 热更新并刷新路由
  if (import.meta.hot) handleHotUpdate(router)
}

export default router
