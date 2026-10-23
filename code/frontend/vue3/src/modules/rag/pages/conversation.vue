<!-- RAG 知识库对话页: 会话侧栏 + 流式问答主区(AG-UI 协议) -->
<template>
  <div flex flex-col h-app w-full bg-note-paper overflow-hidden>
    <div flex flex-1 min-h-0 w-full>
    <!-- 知识库问答: 可收起会话列表 + 居中消息流(过程区块/引用溯源) + 悬浮输入卡 -->
    <!-- 会话列表侧栏(遮罩/分组/搜索/重命名/删除/新建入口内聚于组件; sidebarOpen 经 v-model 共享) -->
    <ConversationSidebar
      v-model:open="sidebarOpen"
      :conversations="conversations"
      :current-id="currentConversationId"
      @select="selectConversation"
      @create="handleCreateConversation"
      @rename="handleRenameConversation"
      @remove="handleDeleteConversation"
    />

    <!-- 右侧聊天区域 -->
    <section flex-1 flex flex-col min-w-0 relative>
      <!-- 顶部栏: 侧栏开关 + 当前会话标题 -->
      <header
        flex items-center gap-2 px-3 md:px-5 py-2.5
        class="note-edge-b bg-note-soft/70" backdrop-blur
      >
        <button
          rounded-full p-2 transition
          :class="sidebarOpen ? 'bg-note-tint text-note-green' : 'text-note hover:bg-note-tint'"
          :title="sidebarOpen ? '收起会话列表' : '展开会话列表'"
          @click="sidebarOpen = !sidebarOpen"
        >
          <el-icon :size="20">
            <Fold v-if="sidebarOpen" />
            <Expand v-else />
          </el-icon>
        </button>
        <h2 v-if="currentConversation" flex-1 min-w-0 truncate text-sm font-medium text-note m-0 flex items-center gap-2>
          <el-tag
            v-if="currentConversation.agent_id"
            size="small" effect="plain" type="success"
            class="shrink-0"
          >
            {{ agentName(currentConversation.agent_id) }}
          </el-tag>
          <span truncate>{{ currentConversation.title || '新对话' }}</span>
        </h2>
      </header>

      <!-- 消息流: 居中阅读宽度(过程区块/引用溯源/交互卡片 + 富文本) -->
      <ChatMessageList
        ref="messageListRef"
        :messages="messages"
        :streaming-message-id="streamingMessageId"
        :can-load-more="hasMoreMessages"
        flex-1
        @interact="handleInteraction"
        @load-more="handleLoadMoreMessages"
      >
        <!-- 空状态: 问候 + 建议问题卡片 -->
        <template #empty>
          <div class="min-h-[60%]" flex flex-col items-center justify-center py-8 text-center>
            <div w-16 h-16 rounded-2xl bg-note-tint flex-center shadow-note mb-4>
              <el-icon :size="30" text-note-green><ChatDotRound /></el-icon>
            </div>
            <h2 text-xl font-bold text-note>AI 助手</h2>
            <p mt-1 text-sm text-note-sub>{{ agentMode ? `已选择「${agentName(selectedAgentId)}」，助手可自主调用技能完成任务` : '选择关联知识库，回答将基于文档内容生成' }}</p>
            <div grid grid-cols-1 sm:grid-cols-2 gap-2.5 mt-8 w-full max-w-lg>
              <button
                v-for="s in suggestions" :key="s.label"
                flex items-center gap-3 p-3.5 rounded-xl bg-note-card text-left
                hover:shadow-note hover:-translate-y-0.5 transition-all
                @click="applySuggestion(s.question)"
              >
                <div w-8 h-8 rounded-lg bg-note-tint flex-center shrink-0>
                  <el-icon :size="16" text-note-green><component :is="s.icon" /></el-icon>
                </div>
                <div min-w-0>
                  <div text-sm font-medium text-note>{{ s.label }}</div>
                  <div text-xs text-note-sub truncate>{{ s.question }}</div>
                </div>
              </button>
            </div>
          </div>
        </template>
      </ChatMessageList>

      <!-- 输入区: 悬浮卡片式输入框(知识库/思考模式与输入同行) -->
      <div px-3 md:px-4 pb-3 md:pb-4>
        <div max-w-3xl mx-auto>
          <ChatComposer
            v-model="inputMessage"
            :is-sending="isSending"
            :attachments="tempAttachments"
            :accept="TEMP_ACCEPT"
            :attachment-disabled="isSending || agentMode"
            :voice-input="true"
            @send="handleSend"
            @stop="handleStop"
            @files-picked="handleFilesPicked"
            @remove-file="removeAttachment"
          >
            <template #toolbar>
              <!-- 助手选择: 空值=仅知识库问答(原 RAG 链路), 选中后走智能体对话 -->
              <el-select
                v-model="selectedAgentId"
                class="kb-select" size="small"
                :style="{ width: agentMode ? '150px' : '118px' }"
                :disabled="isSending"
                :placeholder="'仅知识库'"
                title="选择助手切换对话模式"
              >
                <el-option label="仅知识库" value="" />
                <el-option v-for="a in agents" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
              <el-select
                v-model="selectedProjectIds" multiple collapse-tags collapse-tags-tooltip :max-collapse-tags="2"
                class="kb-select" size="small" placeholder="关联知识库" :disabled="isSending || agentMode"
              >
                <el-option v-for="p in myProjects" :key="p.project_id" :label="p.project_name" :value="p.project_id" />
              </el-select>
              <!-- 思考模式: 快速回答/深度思考 下拉切换(胶囊触发器, 当前项带勾选) -->
              <el-dropdown
                trigger="click"
                :disabled="agentMode"
                @command="setThinkingMode"
              >
                <button
                  class="think-btn"
                  :class="{ active: deepThinking }"
                  flex items-center gap-1 py-1 px-2.5 rounded-full border border-transparent
                  bg-note-tint text-note-sub hover:text-note text-xs whitespace-nowrap cursor-pointer
                  note-transition
                  :disabled="agentMode"
                  :title="agentMode ? '助手模式下由助手自主决策' : (deepThinking ? '当前：深度思考（更深入的推理分析）' : '当前：快速回答')"
                >
                  <el-icon :size="13"><component :is="deepThinking ? MagicStick : Lightning" /></el-icon>
                  {{ deepThinking ? '思考' : '快速' }}
                  <el-icon :size="10" class="opacity-50"><CaretBottom /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="fast">
                      <span class="mode-item">
                        <el-icon><Lightning /></el-icon>快速
                        <el-icon v-if="!deepThinking" class="mode-check"><Check /></el-icon>
                      </span>
                    </el-dropdown-item>
                    <el-dropdown-item command="deep">
                      <span class="mode-item">
                        <el-icon><MagicStick /></el-icon>思考
                        <el-icon v-if="deepThinking" class="mode-check"><Check /></el-icon>
                      </span>
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <!-- 联网搜索开关: 仅保留地球图标(最通用的联网标识), 激活态白底描边 -->
              <el-tooltip
                :content="agentMode ? '助手模式下由助手自主决定是否联网' : '开启后回答将结合实时网络搜索结果，并与知识库内容统一精排'"
                placement="top"
              >
                <button
                  class="web-btn"
                  :class="{ active: enableWebsearch }"
                  :aria-pressed="enableWebsearch"
                  :disabled="agentMode"
                  :title="'联网搜索'"
                  @click="!agentMode && (enableWebsearch = !enableWebsearch)"
                >
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                    stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                    <path d="M2 12h20" />
                  </svg>
                </button>
              </el-tooltip>
            </template>
          </ChatComposer>
        </div>
      </div>
    </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted } from 'vue'
// keep-alive 缓存名单(App.vue include 按组件名匹配):
// 对话页为重状态页(会话列表/流式输出/滚动位置), 缓存后切回免整页重建与重拉
defineOptions({ name: 'RagConversation' })
import {
  Fold, Expand, MagicStick, ChatDotRound,
  EditPen, Document, List, DataAnalysis,
  Lightning, CaretBottom, Check,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createConversation,
  listMyConversations,
  listAgentConversations,
  getConversation,
  updateConversation,
  deleteConversation,
  listConversationMessages,
  sendRagChatAguiStream,
  parseTempFile,
} from '../api/conversation'
import { listMyProjects } from '../api/member'
import { listAgents, sendAgentChatAguiStream } from '@/modules/agent/api/agent'
import type { AgentInfo } from '@/modules/agent/types'
import ChatMessageList from '@/common/components/chat/ChatMessageList.vue'
import ChatComposer from '@/common/components/chat/ChatComposer.vue'
import ConversationSidebar from '../components/ConversationSidebar.vue'
import { useAguiMessages } from '@/common/composables/useAguiMessages'
import { StreamEventType } from '@/common/types/chat'
import type { AguiStreamCallbacks } from '@/common/api/aguiStream'
import type { MessageBlock, ChatAttachment } from '@/common/types/chat'
import type {
  InteractionResponsePayload,
  InteractionSpec,
  MessageInteraction,
} from '@/common/types/agui'
import type { Conversation, ChatMessage, MyProject, RagChatRequest } from '../types'

// ===== 会话列表 =====
const conversations = ref<Conversation[]>([])
const currentConversationId = ref<string | null>(null)
// 侧栏开关(桌面默认展开, 移动端默认收起为抽屉; 单一状态经 v-model 与侧栏组件共享)
const sidebarOpen = ref(typeof window !== 'undefined' && window.innerWidth >= 768)

// 当前会话信息(顶栏标题展示)
const currentConversation = computed(() =>
  conversations.value.find((c) => c.id === currentConversationId.value),
)

// ===== 知识库关联 =====
const myProjects = ref<MyProject[]>([])
const selectedProjectIds = ref<string[]>([])

// ===== 智能体(助手)模式 =====
// 可见助手列表(公开+自建); 选中后对话走 /agent/chat 链路, 会话列表切到 scope=agent
const agents = ref<AgentInfo[]>([])
const selectedAgentId = ref('')
const agentMode = computed(() => Boolean(selectedAgentId.value))
const agentName = (id: string) =>
  agents.value.find((a) => a.id === id)?.name ?? '助手'

/** 加载可见助手列表(失败静默, 不阻断知识库问答) */
const loadAgents = async () => {
  try {
    agents.value = await listAgents()
  } catch (error) {
    console.error('获取助手列表失败:', error)
  }
}

// 切换助手: 中止在途流并重载对应范围的会话列表(知识库会话/智能体会话分开)
// restoringAgent: 选中会话时程序恢复助手选择, 跳过重载避免覆盖用户点选的会话
let restoringAgent = false
watch(selectedAgentId, () => {
  if (restoringAgent) {
    restoringAgent = false
    return
  }
  if (isSending.value) abortActiveStream()
  currentConversationId.value = null
  messages.value = []
  tempAttachments.value = []
  loadConversations()
})

// ===== 聊天状态 =====
const messages = ref<ChatMessage[]>([])
// 历史消息分页加载: 首屏取最近一页, 触顶按需向上翻页(长会话避免一次性全量渲染)
const MESSAGE_PAGE_SIZE = 50
const messagePage = ref(1)
const hasMoreMessages = ref(false)
const loadingOlderMessages = ref(false)
const inputMessage = ref('')
const isSending = ref(false)
const deepThinking = ref(false)
const enableWebsearch = ref(false)

/** 思考模式下拉切换: fast=快速回答, deep=深度思考 */
const setThinkingMode = (mode: string | number | object) => {
  deepThinking.value = mode === 'deep'
}
const streamingMessageId = ref<string | null>(null)
const messageListRef = ref<InstanceType<typeof ChatMessageList>>()

// ===== 临时文件附件(不入知识库, 解析后随消息回传) =====
const tempAttachments = ref<ChatAttachment[]>([])
// 附件选择框 accept: 版式文档/图片(走 MinerU) + 纯文本(直读), 与后端白名单一致
const TEMP_ACCEPT = '.pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg,.txt,.md,.csv,.log,.json'
const TEMP_MAX_FILES = 5

/** 选中文件 → 逐个解析(后端异步端点, 全程不阻塞其他接口) */
const handleFilesPicked = async (files: File[]) => {
  for (const f of files) {
    if (tempAttachments.value.length >= TEMP_MAX_FILES) {
      ElMessage.warning(`单条消息最多 ${TEMP_MAX_FILES} 个附件`)
      break
    }
    const att: ChatAttachment = {
      id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: f.name,
      status: 'parsing',
    }
    tempAttachments.value.push(att)
    try {
      const res = await parseTempFile(f)
      att.status = 'ready'
      att.content = res.content
      att.chars = res.chars
      att.truncated = res.truncated
      if (res.truncated) ElMessage.info(`「${f.name}」内容较长，已截断至 ${res.chars} 字符`)
    } catch (e) {
      att.status = 'error'
      att.error = e instanceof Error ? e.message : '解析失败'
      ElMessage.error(`「${f.name}」解析失败: ${att.error}`)
    }
  }
}

const removeAttachment = (id: string) => {
  tempAttachments.value = tempAttachments.value.filter((a) => a.id !== id)
}

// 停止生成(中止 SSE)
let abortController: AbortController | null = null
let stopRequested = false
// 流会话序号: 切换会话/卸载使旧流收尾失效, 防止旧流 finishStream 重置新流的全局发送状态
let streamSeq = 0

/** 中止进行中的流(切换会话/离开页面共用) */
const abortActiveStream = () => {
  streamSeq++ // 旧流 finishStream 检测序号不符即跳过状态重置
  stopRequested = true
  abortController?.abort()
  abortController = null
}

// 组件卸载时中止流(防后台连接与事件写入已卸载组件状态)
onUnmounted(abortActiveStream)

// 空状态建议问题(点击即发送)
const suggestions = [
  { label: '提炼要点', question: '这份文档的核心观点是什么？', icon: markRaw(Document) },
  { label: '总结归纳', question: '帮我总结知识库中的关键信息', icon: markRaw(List) },
  { label: '撰写文稿', question: '根据知识库资料写一份会议纪要', icon: markRaw(EditPen) },
  { label: '对比分析', question: '对比文档中提到的几种方案优劣', icon: markRaw(DataAnalysis) },
]

// 会话分组/搜索展示逻辑已拆至 ConversationSidebar

// ===== 数据加载 =====
// 我可访问的知识库项目
const loadMyProjects = async () => {
  try {
    const res = await listMyProjects({ page: 1, size: 200 })
    myProjects.value = res.items
  } catch (error) {
    console.error('获取知识库列表失败:', error)
  }
}

// 会话列表(默认选中最近一个; 助手模式拉取智能体会话, 知识库模式拉取知识库会话)
const loadConversations = async () => {
  try {
    const fetcher = agentMode.value ? listAgentConversations : listMyConversations
    const res = await fetcher({ page: 1, size: 100 })
    conversations.value = res.items
    if (!currentConversationId.value && conversations.value.length > 0) {
      await selectConversation(conversations.value[0].id)
    }
  } catch (error) {
    console.error('获取对话列表失败:', error)
  }
}

/** 历史消息 blocks 归一化: 后端存 {node_name, stream_event_type, content, data},
 * 补齐 id/type; interaction 块(data 为 InteractionSpec)重建为交互卡片(只读紧凑态) */
const normalizeBlocks = (
  msg: ChatMessage
): { blocks: MessageBlock[]; interactions: MessageInteraction[] } => {
  const blocks: MessageBlock[] = []
  const interactions: MessageInteraction[] = []
  ;(msg.blocks ?? []).forEach((blk, i) => {
    if (blk.stream_event_type === StreamEventType.INTERACTION && blk.data) {
      interactions.push({
        spec: blk.data as unknown as InteractionSpec,
        responded: true,
        response: null,
      })
      return
    }
    if (!blk.content) return
    blocks.push({
      id: blk.id ?? `hist-${msg.id}-${i}`,
      node_name: blk.node_name ?? '',
      type: 'process',
      content: blk.content ?? '',
      stream_event_type: blk.stream_event_type,
      data: blk.data ?? null,
    })
  })
  return { blocks, interactions }
}

/** 历史消息归一化(倒序接口转正序展示, blocks 归一化 + 交互卡片重建) */
const normalizeHistoryMessages = (items: ChatMessage[]): ChatMessage[] =>
  [...items].reverse().map((msg) => {
    if (msg.role !== 'assistant') return msg
    const { blocks, interactions } = normalizeBlocks(msg)
    return { ...msg, blocks, interactions: interactions.length ? interactions : null }
  })

// ===== 会话操作 =====
const handleCreateConversation = async () => {
  try {
    const id = await createConversation({
      title: '新对话',
      project_ids: selectedProjectIds.value,
      agent_id: selectedAgentId.value || undefined,
    })
    await loadConversations()
    await selectConversation(id)
    ElMessage.success('对话已创建')
  } catch (error) {
    console.error('创建对话失败:', error)
    ElMessage.error('创建对话失败')
  }
}

// 选中会话并加载历史消息(桌面保持侧栏展开, 仅移动端抽屉自动收起; 恢复关联知识库/助手与过程区块)
const selectConversation = async (conversationId: string) => {
  // 中止进行中的流(旧流收尾经序号检测失效, 不污染新会话的全局发送状态)
  if (currentConversationId.value !== conversationId) abortActiveStream()
  // 移动端侧栏为遮罩抽屉, 选中后收起露出消息区; 桌面常驻侧栏不收起
  if (window.innerWidth < 768) sidebarOpen.value = false
  currentConversationId.value = conversationId
  messages.value = []
  tempAttachments.value = [] // 切换会话清空未发送的附件(附件仅作用于当前会话)
  try {
    // 会话详情与历史消息为独立请求, 并行拉取(串行等待会叠加白屏时间);
    // 首屏只取最近一页, 更早历史触顶按需加载(避免长会话一次性 200 条全量渲染)
    const [conv, res] = await Promise.all([
      getConversation(conversationId),
      listConversationMessages(conversationId, {
        page: 1,
        size: MESSAGE_PAGE_SIZE,
      }),
    ])
    // 恢复会话绑定的助手(智能体会话切到对应模式, 知识库会话回到仅知识库)
    const convAgentId = conv?.agent_id ?? ''
    if (convAgentId !== selectedAgentId.value) {
      restoringAgent = true
      selectedAgentId.value = convAgentId
    }
    if (conv?.project_ids?.length) {
      selectedProjectIds.value = conv.project_ids
    }
    // 历史消息(倒序接口按时间正序展示, blocks 归一化 + 交互卡片重建)
    messagePage.value = 1
    hasMoreMessages.value = res.total > MESSAGE_PAGE_SIZE
    messages.value = normalizeHistoryMessages(res.items)
    messageListRef.value?.scrollToBottom(true)
  } catch (error) {
    console.error('加载对话失败:', error)
  }
}

/** 触顶加载更早的历史消息(倒序接口取上一页正序 prepend, 视口位置由列表组件锚定) */
const handleLoadMoreMessages = async () => {
  const conversationId = currentConversationId.value
  if (!conversationId || loadingOlderMessages.value || !hasMoreMessages.value) {
    messageListRef.value?.finishPrepend()
    return
  }
  loadingOlderMessages.value = true
  try {
    const res = await listConversationMessages(conversationId, {
      page: messagePage.value + 1,
      size: MESSAGE_PAGE_SIZE,
    })
    // 会话已在请求期间被切换: 丢弃本次结果
    if (currentConversationId.value !== conversationId) return
    messagePage.value += 1
    hasMoreMessages.value = messagePage.value * MESSAGE_PAGE_SIZE < res.total
    messages.value = [...normalizeHistoryMessages(res.items), ...messages.value]
  } catch (error) {
    console.error('加载更早消息失败:', error)
  } finally {
    messageListRef.value?.finishPrepend()
    loadingOlderMessages.value = false
  }
}

// 知识库关联在发送请求时携带(即时反馈见 ChatComposer 工具栏)

/** 重命名会话(弹窗输入新标题; 触发入口在 ConversationSidebar) */
const handleRenameConversation = async (conv: Conversation) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的对话标题', '重命名对话', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: conv.title || '',
      inputPattern: /\S+/,
      inputErrorMessage: '标题不能为空',
    })
    await updateConversation(conv.id, { title: value.trim() })
    conv.title = value.trim()
    ElMessage.success('已重命名')
  } catch {
    // 用户取消
  }
}

const handleDeleteConversation = async (conv: Conversation) => {
  try {
    await ElMessageBox.confirm(
      `确定删除对话"${conv.title || '新对话'}"吗？`,
      '删除对话',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteConversation(conv.id)
    if (currentConversationId.value === conv.id) {
      currentConversationId.value = null
      messages.value = []
    }
    await loadConversations()
    ElMessage.success('删除成功')
  } catch (error) {
    console.log('取消删除或删除失败:', error)
  }
}

// 点击建议问题直接发送
const applySuggestion = (question: string) => {
  inputMessage.value = question
  handleSend()
}

// ===== 发送/停止(AG-UI 协议) =====
// AG-UI 事件聚合器: 流式期间把事件聚合为 content/blocks/interactions
const {
  message: aguiMessage,
  applyEvent: applyAguiEvent,
  reset: resetAguiMessage,
} = useAguiMessages()

/** 交互响应在用户侧的展示文案(与后端可读兜底一致, 历史与实时观感统一) */
const interactionDisplayText = (payload: InteractionResponsePayload): string => {
  if (payload.value) return payload.value
  if (payload.action === 'skip') return '（跳过补充，请基于现有信息回答）'
  if (payload.action === 'answer_directly')
    return '（无需知识库，请直接用你的知识回答我的上一个问题）'
  if (payload.action === 'rephrase') return '请基于知识库重新检索并回答我之前的问题'
  return '（补充信息）'
}

/** 发起一次 AG-UI 流式请求(普通提问 / 交互响应续跑共用)
 * userBlocks: 用户消息附件标记(temp_file 块, 气泡上方渲染附件芯片, 历史恢复同样生效) */
const startStream = async (
  request: RagChatRequest,
  userDisplay: string,
  userBlocks?: MessageBlock[] | null,
) => {
  if (!currentConversationId.value || isSending.value) return

  const mySeq = ++streamSeq // 本流序号(收尾时校验, 防旧流重置新流状态)

  // 用户消息(交互响应时为可读兜底文案)
  messages.value.push({
    id: `local-${Date.now()}`,
    conversation_id: currentConversationId.value,
    role: 'user',
    content: userDisplay,
    created_at: new Date().toISOString(),
    blocks: userBlocks ?? null,
  })

  // 助手消息占位(流式填充正文/过程区块/交互卡片)
  const assistantMsg: ChatMessage = reactive({
    id: `local-${Date.now() + 1}`,
    conversation_id: currentConversationId.value,
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

  // AG-UI 事件回调组(助手/知识库两条链路共用: 聚合 → 同步到助手占位消息)
  const streamCallbacks: AguiStreamCallbacks = {
    onEvent: (event) => {
      applyAguiEvent(event)
      assistantMsg.content = aguiMessage.content
      assistantMsg.blocks = aguiMessage.blocks
      assistantMsg.interactions = aguiMessage.interactions
    },
    onError: (error: string) => {
      if (!stopRequested) assistantMsg.content += `\n\n> [错误] ${error}`
    },
    onComplete: () => {
      loadConversations()
      // 首次问答后后端异步生成标题, 延迟再刷新一次让侧栏标题跟进
      if (messages.value.length === 2) window.setTimeout(loadConversations, 3000)
    },
    onController: (controller: AbortController) => {
      abortController = controller
    },
  }

  // 结束收尾(幂等; 序号不符说明已被切换会话/新流接管, 跳过全局状态重置)
  const finishStream = () => {
    if (mySeq !== streamSeq) return
    streamingMessageId.value = null
    isSending.value = false
    // 空回复兜底提示(交互-only run 有交互卡片, 不算空回复)
    if (
      !assistantMsg.content &&
      !(assistantMsg.blocks?.length) &&
      !(assistantMsg.interactions?.length)
    ) {
      assistantMsg.content = stopRequested ? '（已停止生成）' : '（未收到回复，请重试）'
    }
    messageListRef.value?.scrollToBottom(true)
  }

  try {
    // 助手模式走智能体执行循环(tool-calling), 其余走知识库问答链路(行为不变)
    const convAgentId = currentConversation.value?.agent_id ?? ''
    const agentId = agentMode.value ? (selectedAgentId.value || convAgentId) : ''
    if (agentId) {
      await sendAgentChatAguiStream(
        currentConversationId.value,
        { message: request.message ?? '', agent_id: agentId },
        streamCallbacks,
      )
    } else {
      await sendRagChatAguiStream(currentConversationId.value, request, streamCallbacks)
    }
  } catch {
    if (!stopRequested) assistantMsg.content += '\n\n> [发送失败，请重试]'
  } finally {
    finishStream()
  }
}

// 发送消息(流式接收; 无会话时自动创建)
const handleSend = async () => {
  const message = inputMessage.value.trim()
  if (!message || isSending.value) return
  if (tempAttachments.value.some((a) => a.status === 'parsing')) {
    ElMessage.warning('附件解析中，请稍候再发送')
    return
  }
  // 仅携带解析成功的附件; 发送即消费(内容经 SystemMessage 持久化, 后续追问仍可引用)
  const readyFiles = tempAttachments.value.filter((a) => a.status === 'ready' && a.content)
  const attachBlocks: MessageBlock[] | null = readyFiles.length
    ? readyFiles.map((a) => ({
        id: `blk-${a.id}`,
        node_name: '',
        type: 'process',
        content: a.name,
        stream_event_type: StreamEventType.TEMP_FILE,
        data: null,
      }))
    : null

  // 无会话时自动创建(标题取首条消息; 助手模式会话绑定 agent_id), 现代聊天交互: 直接输入即可开始
  if (!currentConversationId.value) {
    try {
      const id = await createConversation({
        title: message.slice(0, 20),
        project_ids: selectedProjectIds.value,
        agent_id: selectedAgentId.value || undefined,
      })
      currentConversationId.value = id
      loadConversations()
    } catch (error) {
      console.error('创建对话失败:', error)
      ElMessage.error('创建对话失败')
      return
    }
  }

  inputMessage.value = ''
  tempAttachments.value = []
  await startStream(
    {
      message,
      project_ids: selectedProjectIds.value,
      deep_thinking: deepThinking.value,
      enable_websearch: enableWebsearch.value,
      temp_files: readyFiles.map((a) => ({ name: a.name, content: a.content ?? '' })),
    },
    message,
    attachBlocks,
  )
}

/** 交互卡片响应回传(伪中断续跑): 标记已响应后以 interaction_response 发起流 */
const handleInteraction = (messageId: string, payload: InteractionResponsePayload) => {
  if (isSending.value) return
  const msg = messages.value.find((m) => m.id === messageId)
  const ia = msg?.interactions?.find(
    (i) => i.spec.interaction_id === payload.interaction_id,
  )
  if (!ia || ia.responded) return
  ia.responded = true
  ia.response = payload
  startStream(
    { message: '', interaction_response: { ...payload } },
    interactionDisplayText(payload),
  )
}

// 停止生成(中止 SSE 请求)
const handleStop = () => {
  stopRequested = true
  abortController?.abort()
}

onMounted(() => {
  loadMyProjects()
  loadAgents()
  loadConversations()
})
</script>

<style scoped>
/* 思考模式胶囊按钮: 静态样式已 UnoCSS 化到模板, 此处仅保留依赖 JS 状态类的激活态 */
.think-btn.active {
  background: var(--el-bg-color, #fff);
  border-color: var(--note-green, #6cbf8f);
  color: var(--note-green, #6cbf8f);
}

/* 联网搜索图标按钮: 28px 圆形, 激活态白底描边(与思考按钮激活态一致) */
.web-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 9999px;
  border: 1px solid transparent;
  background: var(--note-tint, #e7f3e9);
  color: var(--note-sub, #6b7f6e);
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s,
    box-shadow 0.2s;
}

.web-btn:hover {
  color: var(--note, #37503c);
}

.web-btn.active {
  background: var(--el-bg-color, #fff);
  border-color: var(--note-green, #6cbf8f);
  color: var(--note-green, #6cbf8f);
}
</style>

<style>
/* 下拉菜单传送至 body, 菜单项布局需全局作用域: 图标+文字+勾选横排 */
.mode-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.mode-item .mode-check {
  margin-left: 12px;
  color: var(--note-green, #6cbf8f);
}
</style>
