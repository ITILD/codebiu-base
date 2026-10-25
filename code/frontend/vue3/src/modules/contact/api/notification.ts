// 通知中心 API(REQ-011: 站内信自助操作 + 订阅开关 + SSE 实时通知流)
import { http_base_server } from '@/common/api/http'
import { API_PREFIX, authFetch } from '@/common/api/authFetch'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import type { NotificationMessage, NotificationSubscription, NotificationSubscriptionSave } from '../types/notification'

/** SSE 通知事件负载(与站内信列表项同构) */
export type ContactMessageResponse = NotificationMessage

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

// ################ SSE 实时通知流 ################

/** 解析后的 SSE 帧 */
export interface SseFrame {
  /** 事件名(未声明时为 message) */
  event: string
  /** data 字段(多行 data 以 \n 连接) */
  data: string
}

/** 增量解析结果: frames 为已完整帧, rest 为需与下次文本拼接的残留 */
export interface SseParseResult {
  frames: SseFrame[]
  rest: string
}

/** 解析单个 SSE 帧(注释行/无 data 的心跳帧返回 null) */
function parseSseFrame(block: string): SseFrame | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    const raw = colon === -1 ? '' : line.slice(colon + 1)
    // SSE 规范: 字段值前仅去掉一个可选空格
    const value = raw.startsWith(' ') ? raw.slice(1) : raw
    if (field === 'event') event = value || 'message'
    else if (field === 'data') dataLines.push(value)
  }
  return dataLines.length ? { event, data: dataLines.join('\n') } : null
}

/**
 * 增量解析 SSE 文本(支持跨 chunk 半帧)
 * @param buffer 上次未消费的残留文本
 * @param chunk 本次读取的新文本
 */
export function parseSseBuffer(buffer: string, chunk: string): SseParseResult {
  const text = `${buffer}${chunk}`.replace(/\r\n|\r/g, '\n')
  const blocks = text.split('\n\n')
  const rest = blocks.pop() ?? ''
  const frames: SseFrame[] = []
  for (const block of blocks) {
    const frame = parseSseFrame(block)
    if (frame) frames.push(frame)
  }
  return { frames, rest }
}

/** 通知流事件回调组 */
export interface NotificationStreamHandlers {
  /** 未读数变化(服务端主动推送的最新未读数) */
  onUnread?: (count: number) => void
  /** 新通知(插入下拉列表头) */
  onNotification?: (payload: ContactMessageResponse) => void
  /** 连接成功(可据此停止轮询兜底) */
  onOpen?: () => void
  /** 连接/读取失败或流被服务端关闭(调用方负责退避重连) */
  onError?: (err: unknown) => void
}

/**
 * 打开实时通知流(fetch 流式读取, 自动携带 Authorization 头)
 * @param handlers 事件回调组
 * @returns 关闭函数(可安全重复调用)
 *
 * 后端事件格式假设:
 *   event: unread       data: {"count": 3}
 *   event: notification data: { id, notify_type, title, content, channels, is_read, created_at }
 *   event: ping         (心跳, 忽略)
 */
export function openNotificationStream(handlers: NotificationStreamHandlers): () => void {
  const controller = new AbortController()
  let closed = false

  /** 分发单帧: 心跳忽略, 非法 JSON 静默丢弃 */
  const dispatch = (frame: SseFrame) => {
    if (frame.event === 'ping') return
    let payload: unknown
    try {
      payload = JSON.parse(frame.data)
    } catch {
      return
    }
    if (frame.event === 'unread') {
      const count = (payload as { count?: unknown } | null)?.count
      if (typeof count === 'number' && Number.isFinite(count)) {
        handlers.onUnread?.(Math.max(0, count))
      }
      return
    }
    if (frame.event === 'notification') {
      if (payload && typeof payload === 'object' && 'id' in payload) {
        handlers.onNotification?.(payload as ContactMessageResponse)
      }
    }
  }

  const run = async () => {
    try {
      const response = await authFetch(`${API_PREFIX}/contact/notifications/stream`, {
        method: 'GET',
        headers: { Accept: 'text/event-stream' },
        cache: 'no-store',
        signal: controller.signal,
      })
      if (!response.ok) {
        throw new Error(`通知流连接失败 (HTTP ${response.status})`)
      }
      if (!response.body) {
        throw new Error('通知流响应不可读')
      }

      handlers.onOpen?.()
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!closed) {
        const { done, value } = await reader.read()
        if (done) {
          // 正常关闭前冲掉解码器与残留帧
          const tail = parseSseBuffer(buffer, `${decoder.decode()}\n\n`)
          tail.frames.forEach(dispatch)
          break
        }
        const parsed = parseSseBuffer(buffer, decoder.decode(value, { stream: true }))
        buffer = parsed.rest
        parsed.frames.forEach(dispatch)
      }

      if (!closed) handlers.onError?.(new Error('通知流已断开'))
    } catch (err) {
      // 主动关闭导致的 AbortError 不视为错误
      if (closed) return
      handlers.onError?.(err)
    }
  }

  void run()

  return () => {
    if (closed) return
    closed = true
    controller.abort()
  }
}
