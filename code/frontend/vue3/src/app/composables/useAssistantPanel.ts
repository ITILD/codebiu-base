/**
 * 悬浮 AI 助手面板开关
 * - 入口在可拖动悬浮工具菜单(需登录 + 后台启用)
 * - 面板宿主在 AssistantFloat 中, 两端通过本模块共享状态
 */
import { ref } from 'vue'

/** 面板是否打开 */
const open = ref(false)
/** 面板是否已挂载(首次打开才加载异步组件, 关闭后仅隐藏以保留会话) */
const mounted = ref(false)
/** 面板吸附方向: 跟随悬浮球所在侧 */
const side = ref<'left' | 'right'>('right')

export function useAssistantPanel() {
  /** 打开面板(anchor 指定面板贴左/贴右) */
  const openPanel = (anchor: 'left' | 'right' = 'right') => {
    side.value = anchor
    mounted.value = true
    open.value = true
  }

  /** 关闭面板(保留已挂载的会话状态) */
  const closePanel = () => {
    open.value = false
  }

  return { open, mounted, side, openPanel, closePanel }
}
