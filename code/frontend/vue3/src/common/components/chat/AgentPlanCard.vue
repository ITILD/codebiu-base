<script setup lang="ts">
// 任务清单折叠块(五拍协议, REQ-002 §6.2)
// - 单例: 同一 run 只有一份清单, 全量替换 + 验收就地更新(投影唯一事实)
// - 状态语义: pending 的第一项即"进行中"; done=已验收; awaiting_human=待人工验收
// - 流式期间默认展开, 结束后折叠; 失败项展示一行原因(可展开看全文)
import { computed, ref, watch } from 'vue'
import { ArrowRight, Check, Loading, User, Warning, Document } from '@element-plus/icons-vue'
import type { AgentPlanItem } from '@/common/types/agui'

interface Props {
  /** 清单项快照(来自 agent.plan_update / verdict 聚合) */
  items: AgentPlanItem[]
  /** 是否处于流式接收中(影响默认展开) */
  streaming?: boolean
}

const props = defineProps<Props>()

const doneCount = computed(
  () => props.items.filter((it) => it.status === 'done').length
)

/** 第一项未完成即"进行中"(少一个状态少一类 bug, 05 §4.2) */
const activeId = computed(
  () => props.items.find((it) => it.status !== 'done')?.id ?? ''
)

const itemIcon = (item: AgentPlanItem): unknown => {
  if (item.status === 'done') return Check
  if (item.status === 'awaiting_human') return User
  return item.id === activeId.value ? Loading : Document
}

const itemClass = (item: AgentPlanItem): string => {
  if (item.status === 'done') return 'is-done'
  if (item.id === activeId.value) return 'is-active'
  return 'is-pending'
}

const collapsed = ref(true)

watch(
  () => props.streaming,
  (streaming) => { collapsed.value = !streaming },
  { immediate: true },
)
</script>

<template>
  <div v-if="items.length" class="mb-2.5 rounded-note-md bg-note-soft overflow-hidden">
    <button
      class="ap-head flex items-center gap-[5px] w-full px-3 py-[5px] border-none bg-transparent text-note-sub text-[11px] cursor-pointer"
      :class="{ open: !collapsed }"
      @click="collapsed = !collapsed"
    >
      <el-icon :size="12" class="shrink-0 opacity-80"><Document /></el-icon>
      <span class="font-medium">任务清单</span>
      <span class="opacity-[.65]">{{ doneCount }}/{{ items.length }} 项已验收</span>
      <el-icon :size="11" class="ml-auto transition-transform" :class="!collapsed ? 'rotate-90' : ''">
        <ArrowRight />
      </el-icon>
    </button>

    <div v-show="!collapsed" class="px-3 pt-0.5 pb-2 flex flex-col gap-[4px]">
      <div
        v-for="item in items"
        :key="item.id"
        class="flex items-start gap-[5px] text-[11px] leading-[1.65] opacity-[.92]"
        :class="itemClass(item)"
      >
        <el-icon :size="11" class="shrink-0 mt-[3px] opacity-80">
          <component :is="itemIcon(item)" :class="{ 'is-spin': item.id === activeId && item.status !== 'done' }" />
        </el-icon>
        <div class="flex-1 min-w-0 flex flex-col">
          <span class="break-words">{{ item.goal }}</span>
          <!-- 验收标准: 模型只看到一行, 用户也只看到一行 -->
          <span v-if="item.acceptance_spec" class="text-[10px] opacity-60 break-words">
            验收 {{ item.acceptance_kind }}：{{ item.acceptance_spec }}
          </span>
          <!-- 失败原因: 最近一次未通过原因(重试时随任务回灌) -->
          <span
            v-if="item.status !== 'done' && item.last_reason"
            class="flex items-start gap-1 text-[10px] text-[color:var(--el-color-warning,#b88230)]"
            :title="item.last_reason"
          >
            <el-icon :size="10" class="shrink-0 mt-[3px]"><Warning /></el-icon>
            <span class="min-w-0 truncate">{{ item.last_reason }}</span>
          </span>
        </div>
        <span v-if="item.attempts" class="shrink-0 text-[10px] font-mono opacity-55">
          ×{{ item.attempts }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ap-head {
  transition: background 0.15s;
}

.ap-head:hover,
.ap-head.open {
  background: var(--note-tint, #e7f3e9);
  color: var(--note-green-deep, #3f7a52);
}

.is-done {
  color: var(--note-green-deep, #3f7a52);
}

.is-active {
  color: var(--note-deep, #2f5d45);
  font-weight: 500;
}

.is-pending {
  color: var(--el-text-color-secondary, #7c8b80);
}

/* 进行中的图标旋转(纯装饰, 不影响可访问性) */
.is-spin {
  animation: ap-spin 1.2s linear infinite;
}

@keyframes ap-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
