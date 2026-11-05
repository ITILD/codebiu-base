<script setup lang="ts">
/**
 * 悬浮 AI 助手小窗(仅面板, 入口在可拖动悬浮工具菜单中)
 * - 仅登录且后台配置启用时渲染; 完整 AI 助手页(/rag/conversation)内整体隐藏
 * - 面板异步懒加载, 首次打开才挂载, 之后关闭仅 v-show 隐藏以保留会话状态
 * - 支持每浏览器会话延迟自动弹开一次(受 autoOpen 配置控制)
 */
defineOptions({ name: 'AssistantFloat' })

import { computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import NoteSkeleton from '@/common/components/NoteSkeleton.vue'
import { useAuthStore } from '@/common/stores/auth'
import { useAssistantPanel } from '@/app/composables/useAssistantPanel'
import {
  ASSISTANT_AUTO_OPEN_FLAG_KEY,
  assistantConfig,
} from '@/modules/ai/utils/assistantConfig'
import { i18n } from '@/common/i18n/language'

const { t } = i18n.global
const route = useRoute()
const authStore = useAuthStore()

const { open, mounted: panelMounted, side, openPanel, closePanel } = useAssistantPanel()

// 面板异步加载: 首次打开时才拉取面板代码
const Panel = defineAsyncComponent(
  () => import('@/modules/rag/components/AssistantWidgetPanel.vue'),
)

/** 是否可用: 已登录 + 配置启用 + 不在完整对话页 */
const visible = computed(
  () =>
    Boolean(authStore.authState.user.id) &&
    assistantConfig.value.enabled &&
    route.path !== '/rag/conversation',
)

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
    openPanel(assistantConfig.value.position)
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

// 离开可用范围(退出登录/关闭配置/进入完整对话页)时一并收起
watch(visible, (next) => {
  if (!next) closePanel()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  if (autoOpenTimer) clearTimeout(autoOpenTimer)
})
</script>

<template>
  <Transition name="asst-pop">
    <div
      v-if="visible"
      v-show="open"
      class="asst-panel"
      :class="side === 'left' ? 'asst-panel--left' : 'asst-panel--right'"
      role="dialog"
      aria-modal="true"
      :aria-label="t('asst_widget_title')"
    >
      <Suspense>
        <Panel v-if="panelMounted" @close="closePanel" />
        <template #fallback>
          <div class="flex h-full w-full flex-col gap-2 bg-note-paper p-3">
            <NoteSkeleton variant="post" />
            <NoteSkeleton variant="post" />
          </div>
        </template>
      </Suspense>
    </div>
  </Transition>
</template>

<style scoped>
/* 小窗: 紧凑尺寸, 贴近微信浮窗的聊天观感 */
.asst-panel {
  position: fixed;
  z-index: 60;
  display: flex;
  flex-direction: column;
  width: min(340px, calc(100vw - 24px));
  height: min(500px, calc(100vh - 6rem));
  right: 12px;
  bottom: calc(12px + var(--note-safe-b, 0px));
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--note-border);
  background: var(--note-paper);
  box-shadow: var(--note-shadow-hover);
  transform-origin: bottom right;
}

.asst-panel--left {
  right: auto;
  left: 12px;
  transform-origin: bottom left;
}

/* 手机(<640px): 宽度铺满留边, 高度约七成屏, 保留浮窗而不是全屏 */
@media (max-width: 639px) {
  .asst-panel {
    left: 8px;
    right: 8px;
    width: auto;
    height: min(68vh, 540px);
    bottom: calc(8px + var(--note-safe-b, 0px));
    border-radius: 14px;
  }

  .asst-panel--left {
    left: 8px;
    right: 8px;
  }
}

/* 弹出/收起: 仅显式过渡 opacity 与 transform */
.asst-pop-enter-active,
.asst-pop-leave-active {
  transition:
    opacity 0.18s ease-out,
    transform 0.18s ease-out;
}

.asst-pop-enter-from,
.asst-pop-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.97);
}
</style>
