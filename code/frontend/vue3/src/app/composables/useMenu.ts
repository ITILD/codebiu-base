/**
 * 可见菜单 composable: 按权限码过滤菜单树
 * 共用方: SysSidebar(后台侧边栏) / 后台概览页快捷入口 / 头像下拉"后台管理"入口
 * / 首页入口卡(useVisibleHome)
 *
 * 导航模型: 所有功能页都是后台侧边栏的末级子项; 标记 home 的末级页面
 * 额外出现在首页入口卡, 点击后以 ?bare=1 单页模式进入(见 menu.ts homeLink)。
 */
import { computed } from 'vue'
import { adminMenuItems, homeEntries } from '@/app/config/menu'
import type { HomeEntry, MenuItem } from '@/app/config/menu'
import { usePermission } from '@/common/composables/usePermission'
import { useAuthStore } from '@/common/stores/auth'

/** 按权限码过滤后的可见后台菜单(未声明 perm 的项登录即可见) */
export function useVisibleMenu() {
  const { hasPerm } = usePermission()

  const visibleMenuItems = computed<MenuItem[]>(() => {
    return adminMenuItems
      .map((item) => {
        // 目录自身声明了权限码: 无权限直接隐藏整组
        if (item.perm && !hasPerm(item.perm)) return null
        // 子菜单逐项过滤(声明了 perm 的子项需有权限; admin: false 的项不进侧边栏)
        if (item.children) {
          const children = item.children.filter(
            (c) => c.admin !== false && (!c.perm || hasPerm(c.perm)),
          )
          if (children.length === 0) return null
          return { ...item, children }
        }
        return item
      })
      .filter((item): item is MenuItem => item !== null)
  })

  return { visibleMenuItems }
}

/**
 * 首页入口过滤(首页入口卡使用):
 * 未登录全部展示(点击后由路由守卫引导登录); 登录后按权限码过滤,
 * 无权限的入口不展示, 避免进入后接口 401
 */
export function useVisibleHome() {
  const { hasPerm } = usePermission()
  const authStore = useAuthStore()

  const visibleHomeEntries = computed<HomeEntry[]>(() => {
    // 未登录: 全部展示(首页是门面, 引导登录后使用)
    if (!authStore.authState.user.id) return homeEntries
    return homeEntries.filter((entry) => !entry.perm || hasPerm(entry.perm))
  })

  return { visibleHomeEntries }
}
