/**
 * v-ellipsis —— 文字溢出时才显示全文提示
 *
 * 背景: 页面里大量 `truncate` / `line-clamp-n` 元素视觉上被截断, 用户却无法
 * 得知完整内容; 无条件写死 `title` 又会在未溢出时也弹出提示, 反而干扰阅读。
 * 本指令只在「内容实际溢出」时挂原生 title(浏览器自带延迟与样式), 文本/尺寸
 * 变化后自动重算, 卸载时还原, 不引入额外 DOM 与第三方 tooltip 开销。
 *
 * 用法:
 *   <span class="truncate" v-ellipsis>{{ title }}</span>        // 单行(已有截断样式)
 *   <p v-ellipsis:2>{{ desc }}</p>                              // 指令自动加两行省略样式
 *   <span v-ellipsis="{ text: fullText, lines: 3 }">…</span>     // 显式文本 + 行数
 *
 * 说明: 未传行数时只托管 title, 不改动元素样式, 适用于页面里已用
 * `truncate` / `line-clamp-n` 处理过截断的场景。
 */
import type { Directive, DirectiveBinding } from 'vue'

/** 指令绑定值(对象写法) */
export interface EllipsisBindingValue {
  /** 提示文本(缺省取元素 textContent) */
  text?: string
  /** 行数: 1 = 单行省略, >=2 = 多行省略 */
  lines?: number
}

interface EllipsisState {
  /** 显式提示文本 */
  text?: string
  /** 行数(0 表示不改动样式, 仅托管 title) */
  lines: number
  /** rAF 句柄(合并同一帧内的多次重算) */
  raf: number
  resizeObserver?: ResizeObserver
  mutationObserver?: MutationObserver
  /** 指令改写过的样式[属性, 原值, 原优先级], 卸载时还原 */
  styleBackup: Array<[string, string, string]>
  /** 挂载时的原始 title(卸载时还原) */
  originalTitle: string | null
}

const stateMap = new WeakMap<HTMLElement, EllipsisState>()

/** 多行省略需要改写的样式(只在传了行数时生效) */
function applyClampStyle(el: HTMLElement, lines: number, state: EllipsisState) {
  const style = el.style
  const set = (prop: string, value: string) => {
    state.styleBackup.push([prop, style.getPropertyValue(prop), style.getPropertyPriority(prop)])
    style.setProperty(prop, value)
  }

  if (lines <= 1) {
    set('overflow', 'hidden')
    set('white-space', 'nowrap')
    set('text-overflow', 'ellipsis')
    return
  }
  set('display', '-webkit-box')
  set('-webkit-box-orient', 'vertical')
  set('-webkit-line-clamp', String(lines))
  set('overflow', 'hidden')
  set('word-break', 'break-word')
}

/** 还原指令改写的样式 */
function restoreStyle(el: HTMLElement, state: EllipsisState) {
  for (const [prop, value, priority] of state.styleBackup.reverse()) {
    if (value) el.style.setProperty(prop, value, priority)
    else el.style.removeProperty(prop)
  }
  state.styleBackup = []
}

/**
 * 判断是否溢出并维护 title
 * 单行看横向溢出, 多行看纵向溢出; 元素隐藏(宽高为 0)时不做判断, 避免误清提示
 */
function measure(el: HTMLElement, state: EllipsisState) {
  if (!el.isConnected || el.clientWidth === 0) return

  const overflowing =
    state.lines <= 1
      ? el.scrollWidth > el.clientWidth + 1
      : el.scrollHeight > el.clientHeight + 1

  const text = (state.text ?? el.textContent ?? '').trim()
  if (overflowing && text) {
    if (el.getAttribute('title') !== text) el.setAttribute('title', text)
    return
  }
  // 未溢出: 恢复原始 title(通常为空, 即彻底移除)
  if (state.originalTitle === null) el.removeAttribute('title')
  else if (el.getAttribute('title') !== state.originalTitle) el.setAttribute('title', state.originalTitle)
}

/** 合并重算: 同一帧内多次触发只执行一次, 避免布局抖动 */
function schedule(el: HTMLElement, state: EllipsisState) {
  if (state.raf) cancelAnimationFrame(state.raf)
  state.raf = requestAnimationFrame(() => {
    state.raf = 0
    measure(el, state)
  })
}

/** 解析绑定值: arg 优先于 value.lines */
function resolveOptions(binding: DirectiveBinding<EllipsisBindingValue | string | undefined>) {
  const value = binding.value
  const fromArg = binding.arg ? Number(binding.arg) : Number.NaN
  const fromValue = typeof value === 'object' && value ? value.lines : undefined
  const lines = Number.isFinite(fromArg) ? fromArg : fromValue ?? 0
  return {
    text: typeof value === 'string' ? value : value?.text,
    lines: lines > 0 ? Math.min(Math.floor(lines), 10) : 0,
  }
}

/** 注册到元素: 首次挂载时建立状态与观察器 */
function setup(el: HTMLElement, binding: DirectiveBinding<EllipsisBindingValue | string | undefined>) {
  const { text, lines } = resolveOptions(binding)
  const state: EllipsisState = {
    text,
    lines,
    raf: 0,
    styleBackup: [],
    originalTitle: el.getAttribute('title'),
  }
  stateMap.set(el, state)

  if (lines > 0) applyClampStyle(el, lines, state)

  // 尺寸变化(窗口缩放/侧栏开合/列宽调整)时重算
  if (typeof ResizeObserver !== 'undefined') {
    state.resizeObserver = new ResizeObserver(() => schedule(el, state))
    state.resizeObserver.observe(el)
  }
  // 文本变化(异步加载/流式输出/切换语言)时重算
  if (typeof MutationObserver !== 'undefined') {
    state.mutationObserver = new MutationObserver(() => schedule(el, state))
    state.mutationObserver.observe(el, {
      childList: true,
      characterData: true,
      subtree: true,
    })
  }

  // 首帧布局完成后再测量, 避免拿到挂载前的 0 尺寸
  schedule(el, state)
}

/** 卸载: 断开观察器并还原样式/title */
function teardown(el: HTMLElement) {
  const state = stateMap.get(el)
  if (!state) return
  if (state.raf) cancelAnimationFrame(state.raf)
  state.resizeObserver?.disconnect()
  state.mutationObserver?.disconnect()
  restoreStyle(el, state)
  if (state.originalTitle === null) el.removeAttribute('title')
  else el.setAttribute('title', state.originalTitle)
  stateMap.delete(el)
}

/** 全局指令: `v-ellipsis` */
export const ellipsisDirective: Directive<HTMLElement, EllipsisBindingValue | string | undefined> = {
  mounted(el, binding) {
    setup(el, binding)
  },
  // 绑定值变化(文案更新/行数切换): 重新解析并重算
  updated(el, binding) {
    const state = stateMap.get(el)
    if (!state) {
      setup(el, binding)
      return
    }
    const { text, lines } = resolveOptions(binding)
    state.text = text
    if (lines !== state.lines) {
      restoreStyle(el, state)
      state.lines = lines
      if (lines > 0) applyClampStyle(el, lines, state)
    }
    schedule(el, state)
  },
  unmounted(el) {
    teardown(el)
  },
}

// 全局指令类型声明(供 Volar 模板类型检查识别 v-ellipsis)
declare module 'vue' {
  interface GlobalDirectives {
    vEllipsis: typeof ellipsisDirective
  }
}
