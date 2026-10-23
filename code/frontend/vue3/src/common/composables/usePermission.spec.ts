// usePermission 单测: 通配符/精确匹配/前缀子权限/未登录拒绝/角色域判断
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// auth store 依赖 authorization api(axios/element-plus 运行时), 测试仅用状态, 打桩隔离
vi.mock('@/modules/authorization/api/auth', () => ({
  getUserPermissions: vi.fn(),
}))

import { usePermission } from './usePermission'
import { useAuthStore } from '@/common/stores/auth'

function loginAs(permissions: string[], roles: Record<string, string[]> = {}) {
  const store = useAuthStore()
  store.authState.user.id = 'u1'
  store.permState.permissions = permissions
  store.permState.roles = roles
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('usePermission.hasPerm', () => {
  it('未登录(无 user.id)一律无权限', () => {
    const store = useAuthStore()
    store.permState.permissions = ['sys:user'] // 即使有残留权限数据
    const { hasPerm } = usePermission()
    expect(hasPerm('sys:user')).toBe(false)
  })

  it('管理员通配符 "*" 拥有任意权限', () => {
    loginAs(['*'])
    const { hasPerm, isAdmin } = usePermission()
    expect(isAdmin.value).toBe(true)
    expect(hasPerm('sys')).toBe(true)
    expect(hasPerm('sys:user:create')).toBe(true)
    expect(hasPerm('anything:else')).toBe(true)
  })

  it('按钮级权限码精确匹配', () => {
    loginAs(['sys:user:create'])
    const { hasPerm, isAdmin } = usePermission()
    expect(isAdmin.value).toBe(false)
    expect(hasPerm('sys:user:create')).toBe(true)
    expect(hasPerm('sys:user:delete')).toBe(false)
  })

  it('菜单级权限码: 拥有任意子权限即视为可见', () => {
    loginAs(['sys:user'])
    const { hasPerm } = usePermission()
    expect(hasPerm('sys')).toBe(true) // 目录级: 存在 sys: 前缀子权限
    expect(hasPerm('sys:user')).toBe(true)
    expect(hasPerm('sys:role')).toBe(false) // 同级其他菜单
    expect(hasPerm('rag')).toBe(false) // 其他模块目录
  })

  it('目录级无任何子权限时不可见', () => {
    loginAs(['sys:user'])
    const { hasPerm } = usePermission()
    expect(hasPerm('task')).toBe(false)
  })
})

describe('usePermission.hasAnyPerm', () => {
  it('任一权限码命中即通过', () => {
    loginAs(['rag:chat'])
    const { hasAnyPerm } = usePermission()
    expect(hasAnyPerm(['sys:user', 'rag:chat'])).toBe(true)
    expect(hasAnyPerm(['sys:user', 'task:queue'])).toBe(false)
    expect(hasAnyPerm([])).toBe(false)
  })
})

describe('usePermission.hasRole', () => {
  it('按域判断角色, 默认全局域', () => {
    loginAs([], { '*': ['admin'], main: ['main_viewer'] })
    const { hasRole } = usePermission()
    expect(hasRole('admin')).toBe(true) // 默认全局域
    expect(hasRole('admin', 'main')).toBe(false)
    expect(hasRole('main_viewer', 'main')).toBe(true)
    expect(hasRole('unknown')).toBe(false)
  })

  it('无角色数据时返回 false', () => {
    loginAs([])
    const { hasRole } = usePermission()
    expect(hasRole('admin')).toBe(false)
  })
})
