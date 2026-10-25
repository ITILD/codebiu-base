<script setup lang="ts">
/**
 * 全局错误边界: 捕获子树渲染/生命周期同步异常, 以「自然笔记」卡片兜底展示。
 * - onErrorCaptured 返回 false 阻断继续冒泡, 避免整站白屏
 * - retry/reset 通过 v-if 切换 + key 递增强制重建插槽子树
 * - 错误堆栈折叠展示, 支持一键复制反馈
 */
import { WarningFilled } from '@element-plus/icons-vue'
import { copyToClipboard } from '@/common/utils/export'
import { i18n } from '@/common/i18n/language'

interface Props {
  /** 自定义标题(缺省使用 err_title 词条) */
  title?: string
  /** 重试回调(先清空错误并重建子树, 再执行该回调) */
  onRetry?: () => void
}

const props = defineProps<Props>()
const { t } = i18n.global

/** 捕获到的异常(原始值, 展示时再归一化) */
const captured = shallowRef<unknown>(null)
/** 是否处于错误态(单独标记, 兼容异常本身为 null 的极端情况) */
const failed = ref(false)
/** 插槽子树重建 key(递增即强制卸载重建) */
const renderKey = ref(0)
/** 复制成功后的短暂反馈 */
const copied = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | null = null

/** 把任意异常归一化为可展示的文本 */
const errorDetail = computed(() => {
  const err = captured.value
  if (err instanceof Error) {
    return {
      message: err.message || err.name,
      stack: err.stack || `${err.name}: ${err.message}`,
    }
  }
  if (typeof err === 'string') return { message: err, stack: err }
  try {
    const text = JSON.stringify(err, null, 2)
    return { message: text, stack: text }
  } catch {
    const text = String(err)
    return { message: text, stack: text }
  }
})

const heading = computed(() => props.title || t('err_title'))

// 捕获子组件异常: 返回 false 阻止继续向父级冒泡(由本组件接管展示)
onErrorCaptured((err, _instance, info) => {
  console.error('[AppErrorBoundary]', info, err)
  captured.value = err
  failed.value = true
  return false
})

/** 清空错误态并重建插槽子树 */
const reset = () => {
  failed.value = false
  captured.value = null
  copied.value = false
  renderKey.value += 1
}
defineExpose({ reset })

/** 重试: 重建子树后交由调用方重新拉取数据 */
const retry = () => {
  reset()
  props.onRetry?.()
}

/** 复制错误信息(消息 + 堆栈) */
const handleCopy = async () => {
  const ok = await copyToClipboard(`${errorDetail.value.message}\n\n${errorDetail.value.stack}`)
  if (!ok) return
  copied.value = true
  if (copyTimer) clearTimeout(copyTimer)
  copyTimer = setTimeout(() => {
    copied.value = false
    copyTimer = null
  }, 2000)
}

onBeforeUnmount(() => {
  if (copyTimer) {
    clearTimeout(copyTimer)
    copyTimer = null
  }
})
</script>

<template>
  <!-- 错误态: 纸张卡片 + 淡苔绿提示 -->
  <div v-if="failed" class="w-full p-4 md:p-6">
    <section
      role="alert"
      aria-live="assertive"
      class="mx-auto w-full max-w-2xl rounded-note-md bg-note-card p-5 shadow-note md:p-6"
    >
      <div class="flex items-start gap-3">
        <div
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-note-tint text-note-green"
          aria-hidden="true"
        >
          <el-icon :size="20"><WarningFilled /></el-icon>
        </div>

        <div class="min-w-0 flex-1">
          <h2 class="text-base font-semibold text-note md:text-lg">{{ heading }}</h2>
          <p class="mt-1 text-sm text-note-sub">{{ t('err_desc') }}</p>

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <el-button
              type="primary"
              :aria-label="t('err_retry')"
              @click="retry"
            >
              {{ t('err_retry') }}
            </el-button>
            <el-button
              :aria-label="copied ? t('err_copied') : t('err_copy')"
              @click="handleCopy"
            >
              {{ copied ? t('err_copied') : t('err_copy') }}
            </el-button>
          </div>

          <!-- 错误详情: 可折叠, 等宽小字; pre 自身横向滚动, 不撑破卡片 -->
          <el-collapse v-if="errorDetail.stack" class="mt-4">
            <el-collapse-item :title="t('err_detail')" name="detail">
              <pre
                class="max-h-60 w-full max-w-full overflow-auto rounded-note-sm bg-note-soft p-3 font-mono text-xs leading-relaxed whitespace-pre text-note-sub"
              >{{ errorDetail.stack }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </section>
  </div>

  <!-- 正常态: display:contents 保持插槽在父布局中的原有占位 -->
  <div v-else :key="renderKey" class="contents">
    <slot />
  </div>
</template>
