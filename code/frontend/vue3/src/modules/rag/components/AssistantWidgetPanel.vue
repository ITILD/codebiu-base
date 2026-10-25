<script setup lang="ts">
/**
 * 悬浮 AI 助手对话面板(紧凑版 conversation.vue)
 * - 与完整对话页共用 ChatMessageList / ChatComposer 与 AG-UI 流式链路
 * - 无会话时首条消息自动创建对话; 助手 id / 知识库 / 思考与联网开关取全局配置默认值
 * - 不接入附件与 token 进度条, 保持面板轻量
 */
defineOptions({ name: 'AssistantWidgetPanel' })

import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound,
  Close,
  FullScreen,
  Plus,
  Setting,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ChatMessageList from '@/common/components/chat/ChatMessageList.vue'
import ChatComposer from '@/common/components/chat/ChatComposer.vue'
import { useAguiMessages } from '@/common/composables/useAguiMessages'
import { createConversation, sendRagChatAguiStream } from '@/modules/rag/api/conversation'
import { listAgents, sendAgentChatAguiStream } from '@/modules/agent/api/agent'
import type { AgentInfo } from '@/modules/agent/types'
import { assistantConfig } from '@/modules/ai/utils/assistantConfig'
import { i18n } from '@/common/i18n/language'
import type { ChatMessage, RagChatRequest } from '@/modules/rag/types'
import type { AguiStreamCallbacks } from '@/common/api/aguiStream'
import type { InteractionResponsePayload } from '@/common/types/agui'

const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = i18n.global
const router = useRouter()

// ===== 会话状态 =====
const messages = ref<ChatMessage[]>([])
const conversationId = ref<string | null>(null)
const inputMessage = ref('')
const isSending = ref(false)
const streamingMessageId = ref<string | null>(null)
const messageListRef = ref<InstanceType<typeof ChatMessageList>>()

// 默认对话参数(取全局配置; 新对话时恢复为这些默认项)
const selectedAgentId = ref(assistantConfig.value.agentId)
const selectedProjectIds = ref<string[]>([...assistantConfig.value.projectIds])
const deepThinking = ref(assistantConfig.value.deepThinking)
const enableWebsearch = ref(assistantConfig.value.enableWebsearch)

// 助手列表(仅用于头部展示当前助手名, 失败静默)
const agents = ref<AgentInfo[]>([])
const activeAgentName = computed(
  () => agents.value.find((a) => a.id === selectedAgentId.value)?.name ?? '',
)

// 欢迎语与快捷提问
const greetingText = computed(() => assistantConfig.value.greeting.trim() || t('asst_empty'))
const suggestions = computed(() =>
  assistantConfig.value.suggestions.filter((item) => item.trim() !== ''),
)

// ===== 流式状态(与完整对话页一致: 序号防旧流污染新流) =====
const {
  message: aguiMessage,
  applyEvent: applyAguiEvent,
  reset: resetAguiMessage,
} = useAguiMessages()

let abortController: AbortController | null = null
let stopRequested = false
let streamSeq = 0

/** 中止在途流 */
const abortActiveStream = () => {
  stopRequested = true
  abortController?.abort()
}

/** 发起一次 AG-UI 流式请求(普通提问 / 交互响应续跑共用) */
const startStream = async (request: RagChatRequest, userDisplay: string) => {
  if (!conversationId.value || isSending.value) return

  // 固定本次请求的会话 id(避免后续异步分支中的类型收窄丢失)
  const convId = conversationId.value
  // 本流序号: 收尾时校验, 防止旧流重置新流的状态
  const mySeq = ++streamSeq

  messages.value.push({
    id: `local-${Date.now()}`,
    conversation_id: convId,
    role: 'user',
    content: userDisplay,
    created_at: new Date().toISOString(),
  })

  // 助手占位消息(流式填充正文/过程区块/交互卡片)
  const assistantMsg: ChatMessage = reactive({
    id: `local-${Date.now() + 1}`,
    conversation_id: convId,
    role: 'assistant',
    content: '',
    created_at: new Date().toISOString(),
    blocks: [],
    interactions: [],
  })
  messages.value.push(assistantMsg)
  streamingMessageId.value = assistantMsg.id
  isSending.value = true
  stopRequested = false
  abortController = null
  resetAguiMessage()
  // 新消息入列后滚到底部
  messageListRef.value?.scrollToBottom(true)

  // AG-UI 事件回调组: 聚合结果同步到占位消息
  const streamCallbacks: AguiStreamCallbacks = {
    onEvent: (event) => {
      applyAguiEvent(event)
      assistantMsg.content = aguiMessage.content
      assistantMsg.blocks = aguiMessage.blocks
      assistantMsg.interactions = aguiMessage.interactions
    },
    onError: () => {
      if (!stopRequested) ElMessage.error(t('asst_failed'))
    },
    onController: (controller: AbortController) => {
      abortController = controller
    },
  }

  // 收尾(幂等; 序号不符说明已被新对话/新流接管, 跳过状态重置)
  const finishStream = () => {
    if (mySeq !== streamSeq) return
    streamingMessageId.value = null
    isSending.value = false
    // 空回复兜底(交互-only run 有交互卡片, 不算空回复)
    if (
      !assistantMsg.content &&
      !(assistantMsg.blocks?.length) &&
      !(assistantMsg.interactions?.length)
    ) {
      assistantMsg.content = stopRequested ? t('asst_stopped') : t('asst_no_reply')
    }
    messageListRef.value?.scrollToBottom(true)
  }

  try {
    const agentId = selectedAgentId.value
    if (agentId) {
      await sendAgentChatAguiStream(
        convId,
        { message: request.message ?? '', agent_id: agentId },
        streamCallbacks,
      )
    } else {
      await sendRagChatAguiStream(convId, request, streamCallbacks)
    }
  } catch {
    // 保留已输出内容, 仅提示失败
    if (!stopRequested) ElMessage.error(t('asst_failed'))
  } finally {
    finishStream()
  }
}

/** 发送消息(无会话时自动创建) */
const handleSend = async () => {
  const message = inputMessage.value.trim()
  if (!message || isSending.value) return

  // 无会话时自动创建(标题取首条消息; 助手模式下会话绑定 agent_id)
  if (!conversationId.value) {
    try {
      conversationId.value = await createConversation({
        title: message.slice(0, 20),
        project_ids: selectedProjectIds.value,
        agent_id: selectedAgentId.value || undefined,
      })
    } catch {
      ElMessage.error(t('asst_conversation_failed'))
      return
    }
  }

  inputMessage.value = ''
  await startStream(
    {
      message,
      project_ids: selectedProjectIds.value,
      deep_thinking: deepThinking.value,
      enable_websearch: enableWebsearch.value,
    },
    message,
  )
}

/** 交互卡片响应回传(伪中断续跑): 标记已响应后以 interaction_response 发起流 */
const handleInteraction = (messageId: string, payload: InteractionResponsePayload) => {
  if (isSending.value) return
  const msg = messages.value.find((m) => m.id === messageId)
  const interaction = msg?.interactions?.find(
    (i) => i.spec.interaction_id === payload.interaction_id,
  )
  if (!interaction || interaction.responded) return
  interaction.responded = true
  interaction.response = payload
  startStream(
    { message: '', interaction_response: { ...payload } },
    payload.value || '（补充信息）',
  )
}

/** 停止生成(中止 SSE 请求) */
const handleStop = () => {
  if (!isSending.value) return
  abortActiveStream()
}

/** 新对话: 中止在途流并清空会话, 保留配置默认项 */
const handleNewChat = () => {
  if (isSending.value) abortActiveStream()
  // 递增序号, 让在途流的收尾逻辑失效
  streamSeq += 1
  messages.value = []
  conversationId.value = null
  streamingMessageId.value = null
  isSending.value = false
  abortController = null
  // 保持 stopRequested=true, 让在途流的中止/异常回调静默(下次发送时 startStream 会重置)
  inputMessage.value = ''
  selectedAgentId.value = assistantConfig.value.agentId
  selectedProjectIds.value = [...assistantConfig.value.projectIds]
  deepThinking.value = assistantConfig.value.deepThinking
  enableWebsearch.value = assistantConfig.value.enableWebsearch
  resetAguiMessage()
}

/** 点击快捷提问直接发送 */
const applySuggestion = (question: string) => {
  inputMessage.value = question
  handleSend()
}

/** 前往完整对话页并收起面板 */
const openFullConversation = () => {
  router.push('/rag/conversation')
  emit('close')
}

/** 前往助手设置并收起面板 */
const openAssistantSettings = () => {
  router.push('/ai/assistant')
  emit('close')
}

/** 加载可见助手列表(仅取名称; 失败静默) */
const loadAgents = async () => {
  try {
    agents.value = await listAgents()
  } catch {
    agents.value = []
  }
}

onMounted(loadAgents)
onUnmounted(abortActiveStream)
</script>

<template>
  <div class="flex h-full w-full min-w-0 flex-col overflow-hidden bg-note-paper">
    <!-- 头部: 标题 + 当前助手名 + 操作按钮(44px 触控区) -->
    <header class="flex h-12 shrink-0 items-center gap-1 border-b border-note bg-note-soft/60 px-2">
      <div class="flex min-w-0 flex-1 items-center gap-2">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-note-tint text-note-green">
          <el-icon :size="17"><ChatDotRound /></el-icon>
        </span>
        <span v-ellipsis class="min-w-0 truncate text-sm font-medium text-note">{{ t('asst_widget_title') }}</span>
        <span v-if="activeAgentName" v-ellipsis class="hidden min-w-0 shrink truncate text-xs text-note-sub sm:inline">
          · {{ activeAgentName }}
        </span>
      </div>
      <button
        type="button"
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-none bg-transparent text-note-sub cursor-pointer note-transition hover:bg-note-tint hover:text-note-green"
        :aria-label="t('asst_new_chat')"
        :title="t('asst_new_chat')"
        @click="handleNewChat"
      >
        <el-icon :size="17"><Plus /></el-icon>
      </button>
      <button
        type="button"
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-none bg-transparent text-note-sub cursor-pointer note-transition hover:bg-note-tint hover:text-note-green"
        :aria-label="t('asst_expand')"
        :title="t('asst_expand')"
        @click="openFullConversation"
      >
        <el-icon :size="17"><FullScreen /></el-icon>
      </button>
      <button
        type="button"
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-none bg-transparent text-note-sub cursor-pointer note-transition hover:bg-note-tint hover:text-note-green"
        :aria-label="t('asst_settings')"
        :title="t('asst_settings')"
        @click="openAssistantSettings"
      >
        <el-icon :size="17"><Setting /></el-icon>
      </button>
      <button
        type="button"
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-none bg-transparent text-note-sub cursor-pointer note-transition hover:bg-note-tint hover:text-note-green"
        :aria-label="t('asst_close')"
        :title="t('asst_close')"
        @click="emit('close')"
      >
        <el-icon :size="17"><Close /></el-icon>
      </button>
    </header>

    <!-- 消息区: 空状态展示欢迎语 + 快捷提问 -->
    <ChatMessageList
      ref="messageListRef"
      :messages="messages"
      :streaming-message-id="streamingMessageId"
      class="min-h-0 flex-1"
      @interact="handleInteraction"
    >
      <template #empty>
        <div class="flex flex-col items-center justify-center gap-2 px-2 py-8 text-center">
          <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-note-tint shadow-note">
            <el-icon :size="24" class="text-note-green"><ChatDotRound /></el-icon>
          </div>
          <p class="m-0 text-sm leading-relaxed text-note">{{ greetingText }}</p>
          <div v-if="suggestions.length" class="mt-2 flex w-full flex-col gap-1.5">
            <button
              v-for="s in suggestions"
              :key="s"
              type="button"
              class="w-full rounded-note-md border border-note bg-note-card px-3 py-2 text-left text-xs text-note note-transition hover:border-note-green hover:bg-note-tint"
              @click="applySuggestion(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>
      </template>
    </ChatMessageList>

    <!-- 输入区: 不启用语音输入, 避免面板内录音权限干扰 -->
    <div class="shrink-0 px-2 pb-2 pt-1.5">
      <ChatComposer
        v-model="inputMessage"
        :is-sending="isSending"
        :voice-input="false"
        :placeholder="t('asst_placeholder')"
        @send="handleSend"
        @stop="handleStop"
      />
    </div>
  </div>
</template>
