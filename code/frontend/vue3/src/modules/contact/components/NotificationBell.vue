<!-- 顶栏通知铃铛(REQ-011): 未读数轮询 + 最近通知面板 + 订阅设置 -->
<template>
  <el-popover trigger="click" width="360" placement="bottom-end" @show="openPanel">
    <template #reference>
      <button
        type="button"
        aria-label="通知中心"
        relative
        flex
        items-center
        justify-center
        rounded
        p-2
        text-note
        hover:bg-note-tint
        note-transition
      >
        <el-icon :size="20"><Bell /></el-icon>
        <span
          v-if="unread > 0"
          class="-top-0.5 -right-0.5"
          absolute
          min-w-4
          h-4
          px-0.5
          rounded-full
          bg-red-500
          text-white
          text-10px
          leading-4
          text-center
          box-border
        >
          {{ unread > 99 ? '99+' : unread }}
        </span>
      </button>
    </template>

    <!-- 面板头: 标题 + 全部已读 + 订阅设置 -->
    <div flex items-center justify-between mb-2>
      <span font-semibold>通知</span>
      <div flex items-center gap-1>
        <el-button link size="small" :disabled="unread === 0" @click="handleReadAll">全部已读</el-button>
        <el-button link size="small" @click="subscriptionVisible = true">订阅设置</el-button>
        <el-button link size="small" type="danger" @click="handleClear">清空</el-button>
      </div>
    </div>

    <!-- 最近通知列表 -->
    <el-scrollbar max-height="320px">
      <div v-if="messages.length === 0" py-8 text-center text-sm text-note-sub>暂无通知</div>
      <div
        v-for="msg in messages"
        :key="msg.id"
        flex
        items-start
        gap-2
        px-2
        py-2
        rounded
        cursor-pointer
        hover:bg-note-tint
        @click="handleRead(msg)"
      >
        <span
          mt-1.5
          w-1.5
          h-1.5
          rounded-full
          shrink-0
          :class="msg.is_read ? 'bg-gray-300' : 'bg-blue-500'"
        />
        <div min-w-0 flex-1>
          <div text-sm :class="msg.is_read ? 'text-note-sub' : 'font-medium'" truncate>{{ msg.title }}</div>
          <div v-if="msg.content" text-xs text-note-sub line-clamp-2>{{ msg.content }}</div>
          <div text-xs text-note-sub mt-0.5>{{ formatDateTime(msg.created_at) }}</div>
        </div>
      </div>
    </el-scrollbar>

    <!-- 订阅设置对话框: 通知类型 x 外部通道 开关矩阵 -->
    <el-dialog v-model="subscriptionVisible" title="通知订阅设置" width="420" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="站内通知始终送达; 邮件/短信需在此开启且账户已绑定对应联系方式"
        mb-3
      />
      <el-table :data="subscriptionRows" size="small">
        <el-table-column prop="type_name" label="通知类型" min-width="100" />
        <el-table-column label="邮件" width="80" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="cellState(row, 'email')"
              @change="(v: string | number | boolean) => handleSubscribe(row, 'email', Boolean(v))"
            />
          </template>
        </el-table-column>
        <el-table-column label="短信" width="80" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="cellState(row, 'sms')"
              @change="(v: string | number | boolean) => handleSubscribe(row, 'sms', Boolean(v))"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </el-popover>
</template>

<script setup lang="ts">
import { Bell } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { formatDateTime } from '@/common/utils/datetime'
import { useAuthStore } from '@/common/stores/auth'
import {
  clearNotifications,
  getUnreadCount,
  listNotifications,
  listSubscriptions,
  markAllNotificationsRead,
  markNotificationRead,
  setSubscription,
} from '../api/notification'
import type { NotificationMessage, NotificationSubscription } from '../types/notification'

const authStore = useAuthStore()
const authState = authStore.authState

// 未读数(铃铛角标, 60s 轮询; 请求走 user_id+is_read 复合索引, 开销极低)
const unread = ref(0)
const POLL_INTERVAL = 60_000
let pollTimer: ReturnType<typeof setInterval> | null = null

const refreshUnread = async () => {
  if (!authState.user.id) return
  try {
    const res = await getUnreadCount()
    unread.value = res.count
  } catch {
    // 轮询失败静默(令牌过期等由全局拦截器统一处理)
  }
}

watch(
  () => authState.user.id,
  (id) => {
    if (id) {
      refreshUnread()
      if (!pollTimer) pollTimer = setInterval(refreshUnread, POLL_INTERVAL)
    } else {
      unread.value = 0
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})

// 面板与列表(openPanel 由 popover show 事件触发)
const messages = ref<NotificationMessage[]>([])

const openPanel = async () => {
  try {
    const res = await listNotifications({ page: 1, size: 20 })
    messages.value = res.items
  } catch {
    messages.value = []
  }
}

const handleRead = async (msg: NotificationMessage) => {
  if (msg.is_read) return
  try {
    await markNotificationRead(msg.id)
    msg.is_read = true
    unread.value = Math.max(0, unread.value - 1)
  } catch {
    // 单条已读失败不打断浏览
  }
}

const handleReadAll = async () => {
  await markAllNotificationsRead()
  messages.value.forEach((m) => (m.is_read = true))
  unread.value = 0
}

const handleClear = async () => {
  await clearNotifications()
  messages.value = []
  unread.value = 0
  ElMessage.success('通知已清空')
}

// 订阅矩阵(类型为行, 通道为列; 展平数据重组为行结构)
const subscriptionVisible = ref(false)
const subscriptions = ref<NotificationSubscription[]>([])

watch(subscriptionVisible, async (visible) => {
  if (!visible) return
  try {
    const res = await listSubscriptions()
    subscriptions.value = res
  } catch {
    subscriptions.value = []
  }
})

const subscriptionRows = computed(() => {
  const rows: { notify_type: string; type_name: string }[] = []
  for (const item of subscriptions.value) {
    if (!rows.some((r) => r.notify_type === item.notify_type)) {
      rows.push({ notify_type: item.notify_type, type_name: item.type_name })
    }
  }
  return rows
})

const cellState = (row: { notify_type: string }, channel: 'email' | 'sms') =>
  subscriptions.value.find((s) => s.notify_type === row.notify_type && s.channel === channel)?.enabled ?? false

const handleSubscribe = async (
  row: { notify_type: string },
  channel: 'email' | 'sms',
  enabled: boolean,
) => {
  try {
    await setSubscription({ notify_type: row.notify_type, channel, enabled })
    const target = subscriptions.value.find(
      (s) => s.notify_type === row.notify_type && s.channel === channel,
    )
    if (target) target.enabled = enabled
    ElMessage.success(enabled ? '已订阅' : '已取消订阅')
  } catch {
    // 失败保持原状态(矩阵下次打开重新拉取)
  }
}
</script>
