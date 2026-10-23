// 通知中心类型定义(REQ-011: 站内信 + 订阅开关)

/** 通知通道编码 */
type NotifyChannel = 'inapp' | 'email' | 'sms'

/** 站内信记录(铃铛列表渲染) */
interface NotificationMessage {
  id: number
  /** 通知类型编码(字典 contact_notify_type, 如 task_done) */
  notify_type: string
  title: string
  content: string | null
  /** 实际尝试送达的通道快照 */
  channels: NotifyChannel[]
  is_read: boolean
  created_at: string
}

/** 订阅矩阵单项(通知类型 x 外部通道) */
interface NotificationSubscription {
  notify_type: string
  type_name: string
  channel: Exclude<NotifyChannel, 'inapp'>
  enabled: boolean
}

/** 订阅开关设置请求 */
interface NotificationSubscriptionSave {
  notify_type: string
  channel: Exclude<NotifyChannel, 'inapp'>
  enabled: boolean
}

export type { NotifyChannel, NotificationMessage, NotificationSubscription, NotificationSubscriptionSave }
