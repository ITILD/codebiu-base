<script setup lang="ts">
// 聊天输入区(单行紧凑布局): [+] 上传 | 自适应 textarea | 工具栏(页面注入) | 发送/语音合并按钮
// 附件(临时文件): 最左 + 号多选 → chips 展示解析状态(解析中/已就绪/失败/已截断), 逻辑由页面处理
// 发送/语音合并: 默认发送; 右侧小下拉切换语音输入, 切换后主按钮变为麦克风(流式 ASR 实时转文字)
import {
  Promotion, VideoPause, Plus, CaretBottom, Check,
  Loading, Document, CircleCloseFilled, Microphone,
} from '@element-plus/icons-vue'
import type { ChatAttachment } from '@/common/types/chat'
import { useVoiceInput } from '@/common/composables/useVoiceInput'

interface Props {
  /** 输入内容(v-model) */
  modelValue: string
  /** 占位提示 */
  placeholder?: string
  /** 是否正在生成(显示停止按钮) */
  isSending?: boolean
  /** 是否禁用输入 */
  disabled?: boolean
  /** 底部提示文案 */
  hint?: string
  /** 附件列表(输入卡片内渲染状态芯片) */
  attachments?: ChatAttachment[]
  /** 附件文件选择框 accept(如 '.pdf,.png,.md') */
  accept?: string
  /** 附件选择是否禁用 */
  attachmentDisabled?: boolean
  /** 是否启用语音输入(发送按钮右侧下拉可切换, 流式 ASR 实时转文字填入输入框) */
  voiceInput?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '输入你的问题...',
  isSending: false,
  disabled: false,
  hint: '',
  attachments: () => [],
  accept: '',
  attachmentDisabled: false,
  voiceInput: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  /** 选中文件(页面负责解析与状态回填) */
  (e: 'files-picked', files: File[]): void
  /** 移除附件 */
  (e: 'remove-file', id: string): void
}>()

const canSend = computed(
  () => !!props.modelValue.trim() && !props.isSending && !props.disabled,
)

/** Enter 发送, Shift+Enter 换行 */
const onKeydown = (e: Event | KeyboardEvent) => {
  const ke = e as KeyboardEvent
  if (ke.key === 'Enter' && !ke.shiftKey && !ke.isComposing) {
    ke.preventDefault()
    if (canSend.value) emit('send')
  }
}

const handleSend = () => {
  if (canSend.value) emit('send')
}

const handleStop = () => emit('stop')

const onInput = (value: string) => emit('update:modelValue', value)

// ===== 附件文件选择 =====
const fileInputRef = ref<HTMLInputElement>()
const pickFiles = () => fileInputRef.value?.click()
const onFilesChange = (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (files.length) emit('files-picked', files)
  // 重置 value: 同一文件可重复选择
  input.value = ''
}

// ===== 语音输入(流式 ASR): 开始时记下输入框已有内容, 识别文本实时追加在其后 =====
let voiceBaseText = ''
const { recording: voiceRecording, start: startVoice, stop: stopVoice } = useVoiceInput({
  // 中间结果: 整体替换当前段(实时观感)
  onPartial: (t) => {
    if (!props.disabled && !props.isSending) emit('update:modelValue', voiceBaseText + t)
  },
  // 定稿文本: 追加到已有内容(多段定稿累加)
  onFinal: (t) => {
    voiceBaseText += t
    if (!props.disabled && !props.isSending) emit('update:modelValue', voiceBaseText)
  },
  onError: (m) => ElMessage.error(m),
})

/** 切换语音输入: 未录音→开始(记录输入框基线文本); 录音中→停止 */
const toggleVoice = () => {
  if (voiceRecording.value) {
    stopVoice()
    return
  }
  if (props.isSending || props.disabled) return
  voiceBaseText = props.modelValue
  startVoice()
}

// ===== 发送/语音合并按钮: 默认发送, 小下拉切换语音模式 =====
type SendMode = 'text' | 'voice'
const sendMode = ref<SendMode>('text')

/** 下拉切换输入方式(语音模式时主按钮变为麦克风) */
const setSendMode = (mode: string | number | object) => {
  sendMode.value = mode as SendMode
}

/** 主按钮点击: 文本模式→发送; 语音模式→开始/停止录音 */
const onMainClick = () => {
  if (sendMode.value === 'voice') toggleVoice()
  else handleSend()
}

/** 占位提示: 语音模式给出引导文案(输入框有内容时恢复原占位) */
const shownPlaceholder = computed(() => {
  if (sendMode.value === 'voice' && !props.modelValue) {
    return voiceRecording.value ? '正在聆听，说话即实时转文字…' : '点击右侧麦克风，说话实时转文字'
  }
  return props.placeholder
})

// ===== 多行检测: 文字到达按钮区域(需要换行)时, 按键自动下移一行 =====
const inputRef = ref<{ textarea?: HTMLTextAreaElement } | null>(null)
const mirrorRef = ref<HTMLElement | null>(null)
const isMultiline = ref(false)
// 行布局下的可用输入宽度缓存(避免两种布局间来回抖动)
let rowAvail = 0

// ===== 高度自适应: 手动计算, 不用 EP autosize =====
// autosize 在挂载时测量, 早于 scoped 样式注入(padding 未生效), 会漏算上下 padding 导致空内容就溢出出滚动条
const resizeInput = () => {
  const el = inputRef.value?.textarea
  if (!el) return
  // 清除 EP 挂载时(样式注入前)误算的内联 min-height, 交由 CSS 的 1 行高度(42px)兜底
  el.style.minHeight = ''
  // 先归零再读 scrollHeight, 拿到内容真实需要的高度(含 padding)
  el.style.height = 'auto'
  const h = el.scrollHeight
  const maxH = parseFloat(getComputedStyle(el).maxHeight) || 162
  el.style.height = `${h}px`
  // 未到封顶行数时隐藏溢出(防亚像素误差产生幻影滚动条); 封顶后才允许滚动
  el.style.overflowY = h > maxH ? 'auto' : 'hidden'
}

/** 同步布局状态: 有显式换行或实测换行行数 > 1 → 按键下移 */
const syncMultiline = () => {
  const el = inputRef.value?.textarea
  const mirror = mirrorRef.value
  if (!el || !mirror) return
  const cs = getComputedStyle(el)
  const text = props.modelValue
  // 行布局时刷新可用宽度缓存; 已下移时沿用缓存, 同一段文本状态保持稳定不抖动
  if (!isMultiline.value) {
    rowAvail = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
  }
  if (text.includes('\n')) {
    isMultiline.value = true
    return
  }
  if (rowAvail <= 0) return
  // 隐藏镜像元素按行布局宽度实测换行行数(与浏览器实际渲染一致)
  mirror.style.width = `${rowAvail}px`
  mirror.style.fontFamily = cs.fontFamily
  mirror.style.fontSize = cs.fontSize
  mirror.style.fontWeight = cs.fontWeight
  mirror.style.fontStyle = cs.fontStyle
  mirror.style.letterSpacing = cs.letterSpacing
  mirror.textContent = text
  const lh = parseFloat(cs.lineHeight) || 24
  isMultiline.value = mirror.offsetHeight / lh > 1.5
}

watch(
  () => props.modelValue,
  () => nextTick(() => {
    resizeInput()
    syncMultiline()
  }),
  { immediate: true },
)
onMounted(() => {
  resizeInput()
  syncMultiline()
  // 尺寸变化时重新评估: 覆盖窗口缩放/样式延迟注入(此时 padding 生效会引起尺寸变化)等场景
  const el = inputRef.value?.textarea
  if (el && typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => {
      resizeInput()
      syncMultiline()
    })
    ro.observe(el)
    // 组件卸载时销毁观察器(防泄漏)
    onUnmounted(() => ro.disconnect())
  }
})
</script>

<template>
  <div class="cc-card relative rounded-note-lg bg-[var(--el-bg-color,#fff)] shadow-note transition-shadow duration-200 px-2 py-1.5">
    <!-- 附件芯片行(临时文件解析状态) -->
    <div v-if="attachments.length" class="flex flex-wrap gap-1.5 px-1 pb-1.5">
      <span
        v-for="a in attachments" :key="a.id"
        class="cc-att inline-flex items-center gap-1 max-w-[260px] px-2 py-[3px] rounded-note-md bg-note-tint text-[0.72rem] text-note-deep"
        :title="a.status === 'error' ? a.error : a.name"
      >
        <el-icon :size="12" class="shrink-0" :class="{ spinning: a.status === 'parsing' }">
          <Loading v-if="a.status === 'parsing'" />
          <CircleCloseFilled v-else-if="a.status === 'error'" class="text-[var(--note-seal,#ad563e)]" />
          <Document v-else />
        </el-icon>
        <span class="truncate">{{ a.name }}</span>
        <span v-if="a.status === 'parsing'" class="shrink-0 text-note-sub">解析中</span>
        <span v-else-if="a.status === 'error'" class="shrink-0 text-[var(--note-seal,#ad563e)]">失败</span>
        <span v-else-if="a.truncated" class="shrink-0 text-note-sub" title="内容较长已截断">已截断</span>
        <button
          class="shrink-0 border-none bg-transparent p-0 cursor-pointer text-note-sub hover:text-note"
          title="移除附件" @click="emit('remove-file', a.id)"
        >×</button>
      </span>
    </div>
    <!-- 单行布局: [+] 输入 | 工具栏 发送组; 文字换行时输入占满整行、按键下移一行(stacked 复合态样式在 scoped style) -->
    <div class="cc-row flex items-center gap-1.5" :class="{ stacked: isMultiline }">
      <!-- 上传临时文件(最左侧 + 号) -->
      <el-tooltip content="上传临时文件（解析后作为本次问答上下文，不进入知识库）" placement="top">
        <button
          class="cc-plus flex items-center justify-center w-8 h-8 rounded-full border border-transparent bg-note-tint text-note-sub cursor-pointer note-transition hover:text-note shrink-0"
          :class="{ 'opacity-50 cursor-not-allowed': attachmentDisabled }"
          :disabled="attachmentDisabled"
          @click="pickFiles"
        >
          <el-icon :size="16"><Plus /></el-icon>
        </button>
      </el-tooltip>
      <el-input
        ref="inputRef"
        :model-value="modelValue"
        type="textarea"
        :rows="1"
        :placeholder="shownPlaceholder"
        :disabled="disabled"
        resize="none"
        @update:model-value="onInput"
        @keydown="onKeydown"
      />
      <div class="cc-side flex items-center gap-1.5 shrink-0">
        <div class="cc-toolbar flex items-center gap-1.5 min-w-0">
          <slot name="toolbar">
            <span class="text-xs text-note-sub whitespace-nowrap">{{ hint || 'Enter 发送 · Shift+Enter 换行' }}</span>
          </slot>
        </div>
        <!-- 停止生成(生成中) -->
        <el-tooltip v-if="isSending" content="停止生成" placement="top">
          <button class="cc-btn stop flex items-center justify-center w-9 h-9 rounded-full border border-transparent bg-note-card text-note-sub cursor-pointer note-transition shadow-[0_0_0_1px_var(--note-edge-soft,rgba(107,158,120,0.16))]" @click="handleStop">
            <el-icon :size="16"><VideoPause /></el-icon>
          </button>
        </el-tooltip>
        <!-- 发送/语音合并按钮: 默认发送, 右侧小下拉切换语音输入 -->
        <div
          v-else
          class="cc-send-group"
          :class="{ enabled: sendMode === 'text' && canSend, recording: voiceRecording, 'no-caret': !voiceInput }"
        >
          <button
            class="cc-send-main flex items-center justify-center"
            :disabled="sendMode === 'text' && !canSend"
            :title="sendMode === 'voice'
              ? (voiceRecording ? '停止语音输入（识别文本保留在输入框）' : '开始语音输入')
              : '发送'"
            @click="onMainClick"
          >
            <el-icon :size="16"><Microphone v-if="sendMode === 'voice'" /><Promotion v-else /></el-icon>
          </button>
          <el-dropdown v-if="voiceInput" trigger="click" @command="setSendMode">
            <button class="cc-send-caret flex items-center justify-center" title="切换输入方式">
              <el-icon :size="10"><CaretBottom /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="text">
                  <span class="cc-mode-item">
                    <el-icon><Promotion /></el-icon>发送
                    <el-icon v-if="sendMode === 'text'" class="cc-check"><Check /></el-icon>
                  </span>
                </el-dropdown-item>
                <el-dropdown-item command="voice">
                  <span class="cc-mode-item">
                    <el-icon><Microphone /></el-icon>语音输入
                    <el-icon v-if="sendMode === 'voice'" class="cc-check"><Check /></el-icon>
                  </span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>
    <!-- 行宽镜像(隐藏): 按行布局宽度实测文本换行行数, 决定按键是否下移 -->
    <div ref="mirrorRef" class="cc-mirror absolute top-0 left-0 invisible pointer-events-none whitespace-pre-wrap break-words text-[0.95rem] leading-[24px]" aria-hidden="true"></div>
    <!-- 隐藏文件选择框(附件) -->
    <input ref="fileInputRef" type="file" class="hidden" multiple :accept="accept" @change="onFilesChange" />
  </div>
</template>

<style scoped>
/* 附件解析中图标旋转(Vue/EP 无内置 spin, 动画保留在 style) */
.cc-att .spinning {
  animation: cc-spin 1s linear infinite;
}

/* 发送/语音合并按钮: 主按钮 + 小下拉拼成胶囊, 共用底色 */
.cc-send-group {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
}

.cc-send-main,
.cc-send-caret {
  border: none;
  background: var(--note-tint, #e7f3e9);
  color: var(--note-sub, #6b7f6e);
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s,
    box-shadow 0.2s,
    opacity 0.2s;
  padding: 0;
}

.cc-send-main {
  width: 36px;
  height: 36px;
  border-radius: 999px 0 0 999px;
}

.cc-send-caret {
  width: 18px;
  height: 36px;
  border-radius: 0 999px 999px 0;
  border-left: 1px solid color-mix(in srgb, currentColor 25%, transparent);
}

/* 未启用语音输入: 无小下拉, 主按钮为完整圆形 */
.cc-send-group.no-caret .cc-send-main {
  width: 36px;
  border-radius: 999px;
}

/* 可发送态: 绿底白字(下拉箭头同色, 形成整体胶囊) */
.cc-send-group.enabled .cc-send-main,
.cc-send-group.enabled .cc-send-caret {
  background: var(--note-green, #6cbf8f);
  color: #fff;
  box-shadow: 0 2px 10px rgba(108, 191, 143, 0.4);
}

.cc-send-group.enabled .cc-send-main:hover {
  opacity: 0.9;
}

/* 文本模式下不可发送: 灰化禁用 */
.cc-send-main:disabled {
  background: var(--note-tint, #e7f3e9);
  color: var(--note-sub, #6b7f6e);
  cursor: not-allowed;
  box-shadow: none;
}

/* 语音录音中: 红底白字 + 脉冲光圈提示(状态样式保留在 style) */
.cc-send-group.recording .cc-send-main {
  background: var(--el-color-danger, #f56c6c);
  color: #fff;
  animation: cc-voice-pulse 1.4s ease-out infinite;
}

@keyframes cc-voice-pulse {
  0% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.45); }
  70% { box-shadow: 0 0 0 8px rgba(245, 108, 108, 0); }
  100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0); }
}

@keyframes cc-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 聚焦: 光晕环收拢变亮, 提示输入中(状态选择器, 保留在 style) */
.cc-card:focus-within {
  box-shadow: 0 0 0 2px var(--note-edge-soft, rgba(107, 158, 120, 0.16)), 0 6px 20px -6px var(--note-glow, rgba(107, 158, 120, 0.22));
}

/* 聚焦时的淡渐变光晕: 几乎不可见的流动微光(伪元素 + 动画, 保留在 style) */
.cc-card::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  pointer-events: none;
  background: linear-gradient(
    120deg,
    rgba(108, 191, 143, 0) 0%,
    rgba(108, 191, 143, 0.1) 25%,
    rgba(160, 214, 183, 0.14) 50%,
    rgba(108, 191, 143, 0.1) 75%,
    rgba(108, 191, 143, 0) 100%
  );
  background-size: 250% 100%;
  opacity: 0;
  transition: opacity 0.5s ease;
  animation: cc-glow-flow 4s linear infinite;
  z-index: 0;
}

.cc-card:focus-within::before {
  opacity: 1;
}

/* 光晕之上内容保持可交互(子元素选择器, 保留在 style) */
.cc-card > * {
  position: relative;
  z-index: 1;
}

@keyframes cc-glow-flow {
  0% { background-position: 100% 0; }
  100% { background-position: -150% 0; }
}

/* 同行布局下 el-textarea 占满剩余宽度(子元素选择器, 保留在 style) */
.cc-row > .el-textarea {
  flex: 1 1 auto;
  min-width: 0;
}

/* 多行布局: 输入占满整行, 第二行 + 号居左、工具栏与发送组靠右铺开(动态态 + 子元素联动, 保留在 style) */
.cc-row.stacked {
  flex-wrap: wrap;
}

.cc-row.stacked > .el-textarea {
  order: 1;
  flex-basis: 100%;
}

.cc-row.stacked > .cc-plus {
  order: 2;
}

.cc-row.stacked > .cc-side {
  order: 3;
  flex: 1;
  justify-content: space-between;
}

/* textarea 无边框融入卡片; 行高用整数像素, 避免自适应高度出现亚像素溢出(幻影滚动条) */
/* 高度范围 1~6 行(24px 行高 + 上下 9px padding → 42px/162px), 实际高度由 JS 按内容设置 */
.cc-card :deep(.el-textarea__inner) {
  box-shadow: none !important;
  background: transparent;
  padding: 9px 12px;
  font-size: 0.95rem;
  line-height: 24px;
  border-radius: 0.75rem;
  min-height: 42px;
  max-height: 162px;
}

/* 行宽镜像(隐藏): z 层压到卡片之下(负 z-index, 保留在 style) */
.cc-mirror {
  z-index: -1;
}

.cc-card :deep(.el-textarea__inner)::placeholder {
  color: var(--note-sub, #6b7f6e);
  opacity: 0.7;
}

/* 胶囊形下拉选择器(与思考模式按钮统一风格): :deep 穿透, 保留在 style */
.cc-toolbar :deep(.el-select) {
  width: 140px;
}

.cc-toolbar :deep(.el-select__wrapper) {
  border-radius: 9999px;
  background: var(--note-tint, #e7f3e9);
  box-shadow: none !important;
  border: 1px solid transparent;
  min-height: 28px;
  padding: 2px 10px;
  font-size: 12px;
  transition:
    background-color 0.2s,
    color 0.2s,
    border-color 0.2s,
    box-shadow 0.2s,
    opacity 0.2s;
}

.cc-toolbar :deep(.el-select__wrapper:hover),
.cc-toolbar :deep(.el-select__wrapper.is-focused) {
  border-color: var(--note-border-green, #a9c9b1);
  background: var(--el-bg-color, #fff);
}

.cc-toolbar :deep(.el-select__placeholder) {
  color: var(--note-sub, #6b7f6e);
}

.cc-toolbar :deep(.el-select__selected-item) {
  color: var(--note-green, #6cbf8f);
}

.cc-toolbar :deep(.el-select .el-tag) {
  border-radius: 9999px;
  background: transparent;
  border-color: var(--note-green, #6cbf8f);
  color: var(--note-green, #6cbf8f);
}

/* 停止按钮状态样式(stop, scoped 特异性覆盖 uno 基础类, 保留在 style) */
.cc-btn.stop {
  border-color: var(--note-seal, #ad563e);
  color: var(--note-seal, #ad563e);
}

.cc-btn.stop:hover {
  /* 暖色微底: 由朱砂色混纸底调出, 暗色模式下自动收敛 */
  background: color-mix(in srgb, var(--note-seal, #ad563e) 12%, var(--note-card, #fff));
}
</style>

<style>
/* ---- 全局作用域: 下拉菜单传送至 body, scoped 样式无法命中 ---- */
/* 输入方式菜单项: 图标+文字+勾选横排 */
.cc-mode-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.cc-mode-item .cc-check {
  margin-left: 10px;
  color: var(--note-green, #6cbf8f);
}

/* ---- textarea 滚动条(全局作用域, 避免 scoped 穿透编译差异导致样式失效) ---- */
/* 标准属性(Chromium 121+/Firefox 均支持): 细条无上下箭头; 设置后自动覆盖下方 webkit 规则 */
/* 旧 Chromium 不认识标准属性会忽略, 回退到下方 webkit 自定义规则 */
.cc-card .el-textarea__inner {
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--note-green, #6cbf8f) 40%, transparent) transparent;
}

/* 仅当内容超过6行可滚动时才出现; 细窄圆角、无上下箭头 */
.cc-card .el-textarea__inner::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

/* 显式隐藏上下左右箭头按钮 */
.cc-card .el-textarea__inner::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}

.cc-card .el-textarea__inner::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--note-green, #6cbf8f) 25%, transparent);
  border-radius: 9999px;
}

.cc-card .el-textarea__inner::-webkit-scrollbar-thumb:hover {
  background: color-mix(in srgb, var(--note-green, #6cbf8f) 45%, transparent);
}

.cc-card .el-textarea__inner::-webkit-scrollbar-track,
.cc-card .el-textarea__inner::-webkit-scrollbar-corner {
  background: transparent;
}
</style>
