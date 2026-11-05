/**
 * 批量删除 composable —— 统一后台列表页的多选删除交互
 *
 * 收敛页面重复的: 二次确认 → 删除 → 成功/部分失败提示 → 刷新列表。
 * 后端提供批量接口时传 removeMany, 一次请求完成删除;
 * 否则走 remove 逐条并发删除(Promise.allSettled), 并汇总失败项,
 * 避免"失败被静默吞掉"。
 *
 * 用法:
 *   const { batchDelete, deleting } = useBatchDelete()
 *   batchDelete({
 *     rows: selectedRows.value,
 *     getId: (row) => row.id,
 *     removeMany: (ids) => batchDeleteUsers(ids.map(String)),
 *     label: (row) => row.username,
 *     onRemoved: (n) => refreshAfterRemove(n),
 *   })
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

type EntityId = string | number

interface BatchDeleteOptions<T> {
  /** 待删除行 */
  rows: T[]
  /** 取行主键 */
  getId: (row: T) => EntityId
  /** 单条删除接口(与 removeMany 至少提供一个) */
  remove?: (id: EntityId) => Promise<unknown>
  /** 真正的批量删除接口(优先使用, 一次请求删除全部) */
  removeMany?: (ids: EntityId[]) => Promise<unknown>
  /** 行展示名(用于确认文案与失败汇总) */
  label?: (row: T) => string
  /** 确认框标题(默认「批量删除」) */
  title?: string
  /** 删除成功后回调: 入参为实际成功条数 */
  onRemoved: (removed: number) => void | Promise<void>
}

export function useBatchDelete() {
  const deleting = ref(false)

  /**
   * 执行批量删除(用户取消时静默返回 false)
   * @returns 是否至少删除成功一条
   */
  async function batchDelete<T>(options: BatchDeleteOptions<T>): Promise<boolean> {
    const { rows, getId, remove, removeMany, label, title = '批量删除', onRemoved } = options
    if (!rows.length || deleting.value) return false
    if (!remove && !removeMany) {
      throw new Error('useBatchDelete: 需提供 remove 或 removeMany')
    }

    try {
      await ElMessageBox.confirm(
        `确定删除选中的 ${rows.length} 项吗？此操作不可恢复。`,
        title,
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
      )
    } catch {
      return false // 用户取消
    }

    try {
      deleting.value = true

      // 优先走真正的批量接口: 一次请求, 避免 N 次往返与部分失败
      if (removeMany) {
        try {
          await removeMany(rows.map(getId))
        } catch {
          ElMessage.error('批量删除失败，请重试')
          return false
        }
        ElMessage.success(`已删除 ${rows.length} 项`)
        await onRemoved(rows.length)
        return true
      }

      const results = await Promise.allSettled(rows.map((row) => remove!(getId(row))))
      const ok = results.filter((r) => r.status === 'fulfilled').length
      const failed = results.length - ok

      if (ok > 0) {
        ElMessage.success(failed ? `已删除 ${ok} 项，${failed} 项失败` : `已删除 ${ok} 项`)
        await onRemoved(ok)
      }
      if (failed) {
        // 失败项尽量列出名称, 超过 3 项仅提示数量避免刷屏
        const failedLabels = rows
          .filter((_, i) => results[i].status === 'rejected')
          .map((row) => (label ? label(row) : String(getId(row))))
        const detail = failedLabels.length <= 3 ? `：${failedLabels.join('、')}` : ''
        ElMessage.error(`有 ${failed} 项删除失败${detail}`)
      }
      return ok > 0
    } finally {
      deleting.value = false
    }
  }

  return { batchDelete, deleting }
}
