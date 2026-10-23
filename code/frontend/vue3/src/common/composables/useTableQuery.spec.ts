// useTableQuery 组合式函数单测(REQ-010): 参数合并/末页回退/搜索重置/删除翻页/错误提示
import { describe, it, expect, vi } from 'vitest'

// element-plus 仅用到 ElMessage, 打桩避免 node 环境引入组件库运行时
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { useTableQuery } from './useTableQuery'
import type { PaginationResponse } from '@/common/types/common'

function makeFetcher() {
  return vi.fn(async (params: Record<string, unknown>): Promise<PaginationResponse<unknown>> => {
    const page = params.page as number
    // 第 2 页起返回空(模拟末页空页场景)
    const items = page >= 2 ? [] : Array.from({ length: 3 }, (_, i) => ({ id: `p${page}-${i}` }))
    return { items, total: 3, page, size: 10, pages: 1 }
  })
}

function setup(overrides: Record<string, unknown> = {}) {
  const fetcher = makeFetcher()
  const afterFetch = vi.fn()
  const q = useTableQuery(fetcher, { immediate: false, afterFetch, ...overrides })
  return { q, fetcher, afterFetch }
}

describe('useTableQuery', () => {
  it('fetchData 合并分页与查询参数, 回填表格数据/总数并触发 afterFetch', async () => {
    const { q, fetcher, afterFetch } = setup()
    q.queryParams.value = { keyword: 'abc', is_active: true }
    await q.fetchData()
    expect(fetcher).toHaveBeenCalledWith({ page: 1, size: 10, keyword: 'abc', is_active: true })
    expect(q.tableData.value).toHaveLength(3)
    expect(q.total.value).toBe(3)
    expect(afterFetch).toHaveBeenCalledTimes(1)
  })

  it('末页空页自动回退一页重拉', async () => {
    const { q, fetcher } = setup()
    q.pagination.value.page = 2
    await q.fetchData()
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(fetcher).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))
    expect(q.pagination.value.page).toBe(1)
    expect(q.tableData.value).toHaveLength(3)
  })

  it('handleSearch 回到第一页再拉取', async () => {
    const { q, fetcher } = setup()
    q.pagination.value.page = 5
    q.handleSearch()
    expect(q.pagination.value.page).toBe(1)
    expect(fetcher).toHaveBeenCalledWith(expect.objectContaining({ page: 1 }))
  })

  it('refreshAfterRemove: 当前页仅剩被删条数时先回退一页', async () => {
    const { q, fetcher } = setup()
    q.pagination.value.page = 2
    q.tableData.value = [{ id: 'only' }]
    await q.refreshAfterRemove(1)
    expect(q.pagination.value.page).toBe(1)
    expect(fetcher).toHaveBeenCalled()
  })

  it('拉取失败: ElMessage.error 提示且 loading 复位', async () => {
    const fetcher = vi.fn(async () => {
      throw new Error('boom')
    })
    const q = useTableQuery(fetcher, { immediate: false })
    await q.fetchData()
    expect(ElMessage.error).toHaveBeenCalled()
    expect(q.loading.value).toBe(false)
    expect(q.tableData.value).toHaveLength(0)
  })

  it('竞态守卫: 慢的旧响应后到不得覆盖新请求的结果', async () => {
    // 第 1 页慢(100ms), 第 2 页快(10ms): 旧响应后到, 应被丢弃
    const fetcher = vi.fn(async (params: Record<string, unknown>) => {
      const page = params.page as number
      const items = [{ id: `p${page}` }]
      await new Promise((r) => setTimeout(r, page === 1 ? 100 : 10))
      return { items, total: 2, page, size: 10, pages: 1 }
    })
    const q = useTableQuery(fetcher, { immediate: false })
    const first = q.fetchData()
    q.pagination.value.page = 2
    const second = q.fetchData()
    await Promise.all([first, second])
    expect(q.tableData.value).toEqual([{ id: 'p2' }]) // 而非过期的 p1
    expect(q.loading.value).toBe(false)
  })

  it('竞态守卫: 过期请求的报错不弹提示', async () => {
    const fetcher = vi.fn(async () => {
      throw new Error('boom')
    })
    const q = useTableQuery(fetcher, { immediate: false })
    vi.mocked(ElMessage.error).mockClear() // 排除前序用例的调用计数
    const first = q.fetchData()
    const second = q.fetchData()
    await Promise.all([first, second])
    // 两次都失败, 但仅最新请求的失败弹提示(过期请求静默)
    expect(ElMessage.error).toHaveBeenCalledTimes(1)
  })
})
