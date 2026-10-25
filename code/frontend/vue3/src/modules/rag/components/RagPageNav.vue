<template>
  <!-- AI 助手内页导航: 对话/知识库管理/智能体编排同级(应用页无侧边栏, 孙页面关系由此承担; 按权限过滤) -->
  <nav flex flex-wrap items-center gap-2>
    <RouterLink
      v-for="tab in visibleTabs"
      :key="tab.index"
      :to="tab.index"
      flex
      items-center
      gap-1.5
      px-3.5
      py-1.5
      rounded-full
      text-sm
      note-transition
      :class="isActive(tab.index)
        ? 'bg-note-green text-white font-medium'
        : 'bg-note-tint text-note hover:shadow-note hover:text-note-green'"
    >
      <el-icon :size="14"><component :is="tab.icon" /></el-icon>
      {{ t(tab.titleKey) }}
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { markRaw, computed } from 'vue'
import { useRoute } from 'vue-router'
import { Collection, ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { usePermission } from '@/common/composables/usePermission'
import { i18n } from '@/common/i18n/language'

const { t } = i18n.global

/**
 * AI 助手主应用的三个同级页面
 * - 对话: AI 的最终使用界面(知识库问答 + 智能体对话)
 * - 知识库管理: 文档上传/解析/成员授权
 * - 智能体编排: 助手与技能注册表
 */
const tabs = [
  { index: '/rag/conversation', titleKey: 'asst_nav_chat', icon: markRaw(ChatDotRound), perm: 'rag:chat' },
  { index: '/rag/project', titleKey: 'asst_nav_kb', icon: markRaw(Collection), perm: 'rag:project' },
  { index: '/agent/manage', titleKey: 'asst_nav_agent', icon: markRaw(MagicStick), perm: 'agent:manage' },
]

const route = useRoute()
const { hasPerm } = usePermission()

const visibleTabs = computed(() => tabs.filter((item) => !item.perm || hasPerm(item.perm)))

/** 当前页高亮(文档/成员等子页面按路径前缀匹配) */
function isActive(index: string): boolean {
  return route.path === index || route.path.startsWith(`${index}/`)
}
</script>
