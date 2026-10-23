/**
 * 表格列表查询 composable —— 统一分页列表页的重复模式
 *
 * 收敛此前约 10 个页面/组件重复实现的: 分页参数 / 查询参数 / 表格数据 /
 * loading / fetchData(含末页空页回退) / handleSearch / 删除后翻页回退。
 *
 * 用法(返回值保持 ref 引用, 禁止解构以保响应性):
 *   const { pagination, queryParams, tableData, total, loading, fetchData,
 *           handleSearch, refreshAfterRemove } = useTableQuery(listUsers, {
 *     defaultQuery: { username: '', nickname: '', is_active: undefined },
 *   })
 */
import { ref, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'

/** 列表拉取函数: 接收分页+查询合并参数, 返回标准分页响应 */
type TableFetcher<T> = (
  params: PaginationParams & Record<string, unknown>,
) => Promise<PaginationResponse<T>>

interface UseTableQueryOptions<T> {
  /** 查询参数初始值(与后端列表接口过滤参数对齐) */
  defaultQuery?: Record<string, unknown>
  /** 是否 onMounted 自动拉取(默认 true) */
  immediate?: boolean
  /** 拉取成功后的副作用钩子(如回填行级权限/清空多选) */
  afterFetch?: (items: T[]) => void | Promise<void>
  /** 拉取失败提示文案 */
  errorMsg?: string
}

/**
 * 分页表格查询状态与操作
 * @param fetcher 列表接口
 * @param options 配置项
 */
export function useTableQuery<T>(fetcher: TableFetcher<T>, options: UseTableQueryOptions<T> = {}) {
  const { defaultQuery = {}, immediate = true, afterFetch, errorMsg = '获取数据失败，请重试' } = options

  // 分页参数(模板中 v-model:current-page="pagination.page" 依赖嵌套引用)
  const pagination = ref<PaginationParams>({ page: 1, size: 10 })
  // 查询参数
  const queryParams = ref<Record<string, unknown>>({ ...defaultQuery })
  // 表格数据与总数
  const tableData = ref([]) as Ref<T[]>
  const total = ref(0)
  const loading = ref(false)

  // 请求序号守卫: 快速翻页/连续搜索时旧请求未取消, 慢的旧响应可能后到
  // 覆盖新结果(表格显示过期页), 仅最新请求可写回数据/复位 loading
  let fetchSeq = 0

  /** 拉取列表(内置末页空页回退: page>1 且结果为空时回退一页重拉) */
  const fetchData = async () => {
    const seq = ++fetchSeq
    try {
      loading.value = true
      const response = await fetcher({ ...pagination.value, ...queryParams.value })
      if (seq !== fetchSeq) return // 已有更新的请求在途, 丢弃本次过期结果
      tableData.value = response.items
      total.value = response.total
      if (response.items.length === 0 && pagination.value.page > 1) {
        pagination.value.page -= 1
        await fetchData()
        return
      }
      await afterFetch?.(response.items)
    } catch (error) {
      if (seq !== fetchSeq) return
      console.error('获取列表失败:', error)
      ElMessage.error(errorMsg)
    } finally {
      // 仅最新请求复位 loading(过期请求不得提前解锁新请求的加载态)
      if (seq === fetchSeq) loading.value = false
    }
  }

  /** 搜索: 回到第一页并拉取 */
  const handleSearch = () => {
    pagination.value.page = 1
    fetchData()
  }

  /** 删除后刷新: 当前页仅剩 removed 条且非首页时回退一页 */
  const refreshAfterRemove = async (removed = 1) => {
    if (tableData.value.length <= removed && pagination.value.page > 1) {
      pagination.value.page -= 1
    }
    await fetchData()
  }

  if (immediate) {
    onMounted(fetchData)
  }

  return { pagination, queryParams, tableData, total, loading, fetchData, handleSearch, refreshAfterRemove }
}
