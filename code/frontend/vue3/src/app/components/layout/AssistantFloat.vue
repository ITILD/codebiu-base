<script setup lang="ts">
/**
 * 右下角(可配置左右)悬浮 AI 助手入口
 * - 仅登录且后台配置启用时渲染; 完整 AI 助手页(/rag/conversation)内整体隐藏
 * - 面板异步懒加载, 首次打开才挂载, 之后关闭仅 v-show 隐藏以保留会话状态
 * - 支持每浏览器会话延迟自动弹开一次(受 autoOpen 配置控制)
 */
defineOptions({ name: 'AssistantFloat' })

import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotRound, Close } from '@element-plus/icons-vue'
import NoteSkeleton from '@/common/components/NoteSkeleton.vue'
import { useAuthStore } from '@/common/stores/auth'
import {
  ASSISTANT_AUTO_OPEN_FLAG_KEY,
  assistantConfig,
} from '@/modules/ai/utils/assistantConfig'
import { i18n } from '@/common/i18n/language'

const { t } = i18n.global
const route = useRoute()
const authStore = useAuthStore()

// 面板异步加载: 首次打开时才拉取面板代码
const Panel = defineAsyncComponent(
  () => import('@/modules/rag/components/AssistantWidgetPanel.vue'),
)

const open = ref(false)
const panelMounted = ref(false)
const fabRef = ref<HTMLButtonElement | null>(null)
const panelWrapRef = ref<HTMLElement | null>(null)

/** 是否展示悬浮入口: 已登录 + 配置启用 + 不在完整对话页 */
const visible = computed(
  () =>
    Boolean(authStore.authState.user.id) &&
    assistantConfig.value.enabled &&
    route.path !== '/rag/conversation',
)

/** 打开面板(首次打开才挂载异步组件) */
const openPanel = () => {
  panelMounted.value = true
  open.value = true
}

/** 关闭面板: 焦点在面板内时归还给悬浮按钮 */
const closePanel = () => {
  if (!open.value) return
  const active = document.activeElement
  const focusInPanel =
    active instanceof HTMLElement && Boolean(panelWrapRef.value?.contains(active))
  open.value = false
  if (focusInPanel) nextTick(() => fabRef.value?.focus())
}

const togglePanel = () => {
  if (open.value) closePanel()
  else openPanel()
}

// ===== 自动弹开: 同一浏览器会话仅一次 =====
let autoOpenTimer: ReturnType<typeof setTimeout> | null = null

const hasAutoOpened = () => {
  try {
    return sessionStorage.getItem(ASSISTANT_AUTO_OPEN_FLAG_KEY) === '1'
  } catch {
    return false
  }
}

const markAutoOpened = () => {
  try {
    sessionStorage.setItem(ASSISTANT_AUTO_OPEN_FLAG_KEY, '1')
  } catch {
    /* 隐私模式写入失败时不影响本次弹开 */
  }
}

/** Esc 关闭面板 */
const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && open.value) closePanel()
}

/** 按配置安排一次延迟自动弹开(同一会话仅一次) */
const scheduleAutoOpen = () => {
  if (!visible.value || !assistantConfig.value.autoOpen || hasAutoOpened()) return
  autoOpenTimer = setTimeout(() => {
    if (!visible.value) return
    markAutoOpened()
    openPanel()
  }, 600)
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  scheduleAutoOpen()
})

// 登录是弹窗式(页面不刷新), 登录成功后同样按配置异步弹开一次
watch(
  () => authStore.authState.user.id,
  (userId) => {
    if (userId) scheduleAutoOpen()
  },
)

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  if (autoOpenTimer) clearTimeout(autoOpenTimer)
})
</script>

<template>
  <div v-if="visible">
    <!-- 面板: 桌面固定 400px 宽, 手机全屏 -->
    <Transition name="asst-pop">
      <div
        v-show="open"
        ref="panelWrapRef"
        class="asst-panel"
        :class="assistantConfig.position === 'left' ? 'asst-panel--left' : 'asst-panel--right'"
        role="dialog"
        aria-modal="true"
        :aria-label="t('asst_widget_title')"
      >
        <Suspense>
          <Panel v-if="panelMounted" @close="closePanel" />
          <template #fallback>
            <div class="flex h-full w-full flex-col gap-3 bg-note-paper p-4">
              <NoteSkeleton variant="post" />
              <NoteSkeleton variant="post" />
            </div>
          </template>
        </Suspense>
      </div>
    </Transition>

    <!-- 悬浮按钮: 位置跟随配置, 底部预留安全区 -->
    <button
      ref="fabRef"
      type="button"
      class="asst-fab fixed z-40 flex h-[52px] w-[52px] items-center justify-center rounded-full border-none bg-note-green text-white shadow-note cursor-pointer note-transition hover:shadow-note-hover"
      :class="assistantConfig.position === 'left' ? 'left-5' : 'right-5'"
      :aria-label="open ? t('asst_close') : t('asst_widget_title')"
      :aria-expanded="open"
      :title="open ? t('asst_close') : t('asst_widget_title')"
      @click="togglePanel"
    >
      <el-icon :size="24">
        <Close v-if="open" />
        <ChatDotRound v-else />
      </el-icon>
    </button>
  </div>
</template>

<style scoped>
/* 悬浮按钮: 避开底部安全区(手机 home indicator) */
.asst-fab {
  bottom: calc(1.25rem + var(--note-safe-b, 0px));
}

/* 面板: 桌面/平板固定尺寸, 悬于按钮上方 */
.asst-panel {
  position: fixed;
  /* 高于悬浮按钮, 手机全屏时按钮不会压住面板内容 */
  z-index: 50;
  display: flex;
  flex-direction: column;
  width: 400px;
  height: min(620px, calc(100vh - 7rem));
  bottom: calc(1.25rem + 52px + 0.75rem + var(--note-safe-b, 0px));
  overflow: hidden;
  border-radius: 16px;
  background: var(--note-paper);
  box-shadow: var(--note-shadow-hover);
  transform-origin: bottom right;
}

.asst-panel--right {
  right: 1.25rem;
}

.asst-panel--left {
  left: 1.25rem;
  transform-origin: bottom left;
}

/* 手机(<640px): 全屏面板 */
@media (max-width: 639px) {
  .asst-panel {
    inset: 0;
    width: 100%;
    height: 100%;
    border-radius: 0;
  }
}

/* 弹出/收起: 仅显式过渡 opacity 与 transform */
.asst-pop-enter-active,
.asst-pop-leave-active {
  transition:
    opacity 0.2s ease-out,
    transform 0.2s ease-out;
}

.asst-pop-enter-from,
.asst-pop-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
}
</style>
