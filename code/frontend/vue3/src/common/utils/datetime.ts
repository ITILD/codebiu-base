/**
 * 日期时间格式化 —— 全局统一
 *
 * 收敛此前分散在各页面/组件的内联格式化函数, 统一 zh-CN 展示:
 *   - formatDate: 日期部分(表格列/卡片)
 *   - formatDateTime: 完整时间(详情抽屉/描述列表)
 *   - formatTimeShort: 短时间(表格列省宽场景)
 * @param value ISO 字符串或时间戳字符串; 空值/非法值返回空串
 */

/** 解析为 Date; 非法输入返回 null */
const toDate = (value?: string | null): Date | null => {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** 日期部分 YYYY-MM-DD */
export const formatDate = (value?: string | null): string => {
  const d = toDate(value)
  return d ? d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) : ''
}

/** 完整时间 YYYY-MM-DD HH:mm:ss */
export const formatDateTime = (value?: string | null): string => {
  const d = toDate(value)
  return d ? d.toLocaleString('zh-CN', { hour12: false }) : ''
}

/** 短时间 MM-DD HH:mm(表格列省宽场景) */
export const formatTimeShort = (value?: string | null): string => {
  const d = toDate(value)
  return d
    ? d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : ''
}
