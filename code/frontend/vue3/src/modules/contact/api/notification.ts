// 通知中心 API(REQ-011: 站内信自助操作 + 订阅开关)
import { http_base_server } from '@/common/api/http'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import type { NotificationMessage, NotificationSubscription, NotificationSubscriptionSave } from '../types/notification'

/** 通知列表过滤参数 */
export type NotificationListParams = PaginationParams & {
  /** 已读过滤 */
  is_read?: boolean
}

/**
 * 分页查询我的通知(时间倒序)
 * @param params 分页与过滤参数
 */
export const listNotifications = (params: NotificationListParams) => {
  return http_base_server.get<PaginationResponse<NotificationMessage>>('/contact/notifications/list', { params })
}

/**
 * 未读通知数(铃铛轮询)
 */
export const getUnreadCount = () => {
  return http_base_server.get<{ count: number }>('/contact/notifications/unread-count')
}

/**
 * 标记单条已读
 * @param id 通知ID
 */
export const markNotificationRead = (id: number) => {
  return http_base_server.put<void>(`/contact/notifications/${id}/read`)
}

/**
 * 全部已读
 */
export const markAllNotificationsRead = () => {
  return http_base_server.put<void>('/contact/notifications/read-all')
}

/**
 * 清空我的通知(含已读, 不可恢复)
 */
export const clearNotifications = () => {
  return http_base_server.delete<void>('/contact/notifications')
}

/**
 * 我的订阅矩阵(通知类型 x 通道, 未设置默认关闭)
 */
export const listSubscriptions = () => {
  return http_base_server.get<NotificationSubscription[]>('/contact/notifications/subscriptions')
}

/**
 * 设置单个订阅开关
 * @param data 通知类型 + 通道 + 开关
 */
export const setSubscription = (data: NotificationSubscriptionSave) => {
  return http_base_server.put<NotificationSubscription>('/contact/notifications/subscriptions', data)
}
