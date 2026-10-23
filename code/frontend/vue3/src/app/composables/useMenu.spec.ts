// useMenu 单测: 按权限码过滤后台菜单树/主应用入口, 未登录放行门面入口
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// 隔离 auth store 的 api 依赖(axios/element-plus 运行时)
vi.mock('@/modules/authorization/api/auth', () => ({
  getUserPermissions: vi.fn(),
}))

import { useVisibleMenu, useVisibleApps } from './useMenu'
import { adminMenuItems, mainApps } from '@/app/config/menu'
import { useAuthStore } from '@/common/stores/auth'

function loginAs(permissions: string[]) {
  const store = useAuthStore()
  store.authState.user.id = 'u1'
  store.permState.permissions = permissions
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('useVisibleMenu', () => {
  it('未登录: 仅展示未声明 perm 的分组(声明 perm 的整组隐藏)', () => {
    const { visibleMenuItems } = useVisibleMenu()
    const indexes = visibleMenuItems.value.map((i) => i.index)
    // 无 perm 分组: 首页/系统概览/AI服务/系统监控/模板示例;
    // "/main" 组虽自身无 perm, 但全部子项声明了权限码, 未登录时子项清空 → 整组隐藏
    expect(indexes).toEqual(['/', '/admin', '/ai', '/monitor', '/template'])
  })

  it('管理员("*"): 与 adminMenuItems 全量一致(不含主应用 rag 分组)', () => {
    loginAs(['*'])
    const { visibleMenuItems } = useVisibleMenu()
    expect(visibleMenuItems.value.map((i) => i.index)).toEqual(
      adminMenuItems.map((i) => i.index),
    )
    // 主应用分组(rag)不应出现在后台侧边栏
    expect(visibleMenuItems.value.some((i) => i.index === '/rag')).toBe(false)
  })

  it('子项逐个过滤: 仅拥有部分子权限时分组保留可见子项', () => {
    loginAs(['main:config'])
    const { visibleMenuItems } = useVisibleMenu()
    const main = visibleMenuItems.value.find((i) => i.index === '/main')
    expect(main).toBeDefined()
    expect(main?.children?.map((c) => c.index)).toEqual(['/main/config'])
  })

  it('分组全部子项无权限时整组隐藏', () => {
    loginAs(['sys:user']) // 仅权限管理相关, 任务(task)子项均不可见
    const { visibleMenuItems } = useVisibleMenu()
    expect(visibleMenuItems.value.some((i) => i.index === '/task')).toBe(false)
    expect(visibleMenuItems.value.some((i) => i.index === '/authorization')).toBe(true)
  })
})

describe('useVisibleApps', () => {
  it('未登录: 主应用入口全量展示(门面引导登录)', () => {
    const { visibleApps } = useVisibleApps()
    expect(visibleApps.value.map((a) => a.index)).toEqual(mainApps.map((a) => a.index))
  })

  it('登录且拥有模块权限(或其子权限): 入口可见', () => {
    loginAs(['rag:chat']) // 按钮级权限 → 目录级 rag 视为可见
    const { visibleApps } = useVisibleApps()
    expect(visibleApps.value.map((a) => a.index)).toEqual(['/rag'])
  })

  it('登录但无模块权限: 入口隐藏, 避免进入后 401', () => {
    loginAs(['sys:user'])
    const { visibleApps } = useVisibleApps()
    expect(visibleApps.value).toHaveLength(0)
  })
})
