<template>
  <!-- 移动端抽屉遮罩 -->
  <Transition name="fade">
    <div v-if="open" fixed inset-0 z-20 class="bg-black/30" md:hidden @click="open = false" />
  </Transition>

  <!-- 会话列表(桌面默认常驻可收起, 移动端侧滑抽屉) -->
  <aside
    fixed md:static inset-y-0 left-0 z-30 w-72 shrink-0 flex flex-col bg-note-soft
    class="transition-[transform,margin] duration-300"
    :class="open ? 'translate-x-0 md:ml-0' : '-translate-x-full md:-ml-72'"
  >
    <!-- 新建 + 搜索 -->
    <div p-3 space-y-2.5>
      <button
        class="active:scale-[0.98]"
        flex items-center justify-center gap-1.5 w-full py-2.5 rounded-xl bg-note-green text-white text-sm font-medium
        shadow-note hover:opacity-90 note-transition
        @click="handleCreate"
      >
        <el-icon :size="16"><Plus /></el-icon>
        新建对话
      </button>
      <el-input v-model="searchText" placeholder="搜索对话" size="small" clearable>
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 分组会话列表(今天/昨天/7天内/更早) -->
    <div flex-1 overflow-y-auto px-2 pb-3>
      <template v-for="group in groupedConversations" :key="group.label">
        <div px-3 pt-3 pb-1 text-xs font-medium text-note-sub>{{ group.label }}</div>
        <!-- 行支持键盘操作(Enter/Space 选中), 触屏设备无 hover 时操作按钮常显 -->
        <div
          v-for="conv in group.items" :key="conv.id"
          flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer group transition-colors
          :class="conv.id === currentId
            ? 'bg-note-tint text-note shadow-note'
            : 'text-note-sub hover:bg-note-tint/60'"
          role="button"
          tabindex="0"
          :aria-label="conv.title || '新对话'"
          @click="handleSelect(conv.id)"
          @keydown.enter.prevent="handleSelect(conv.id)"
          @keydown.space.prevent="handleSelect(conv.id)"
        >
          <el-icon :size="15" shrink-0 opacity-70><ChatDotRound /></el-icon>
          <span v-ellipsis flex-1 truncate text-sm>{{ conv.title || '新对话' }}</span>
          <!-- 重命名 -->
          <button
            op-0 group-hover:op-100 group-focus-within:op-100 note-hover-reveal shrink-0 p-1 rounded-md class="hover:bg-note-green/15" hover:text-note-green transition
            title="重命名对话" @click.stop="emit('rename', conv)"
          >
            <el-icon :size="14"><EditPen /></el-icon>
          </button>
          <!-- 删除 -->
          <button
            op-0 group-hover:op-100 group-focus-within:op-100 note-hover-reveal shrink-0 p-1 rounded-md class="hover:bg-red-500/15" hover:text-red-500 transition
            title="删除对话" @click.stop="emit('remove', conv)"
          >
            <el-icon :size="14"><Delete /></el-icon>
          </button>
        </div>
      </template>
      <!-- 空列表 -->
      <div v-if="groupedConversations.length === 0" py-14 text-center text-sm text-note-sub>
        {{ searchText ? '未找到相关对话' : '暂无对话' }}
      </div>
    </div>

    <!-- 次级管理入口(小字低调, 不抢历史列表; 后续智能体管理等在此扩展) -->
    <div v-if="visibleManageLinks.length" class="note-edge-t" px-3 py-2.5 space-y-0.5>
      <RouterLink
        v-for="link in visibleManageLinks" :key="link.index" :to="link.index"
        flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-note-sub
        hover:bg-note-tint hover:text-note-green transition-colors
      >
        <el-icon :size="13"><component :is="link.icon" /></el-icon>
        {{ link.label }}
      </RouterLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
// 会话列表侧栏: 分组/搜索/重命名/删除/新建入口; 会话数据由父级传入,
// 操作经 emit(select/create/rename/remove) 交父级处理; sidebarOpen 经 v-model 共享单一状态(避免双份)
import { computed, markRaw, ref } from 'vue'
import { Plus, Search, ChatDotRound, EditPen, Delete, Collection } from '@element-plus/icons-vue'
import { usePermission } from '@/common/composables/usePermission'
import type { Conversation } from '../types'

const props = defineProps<{
  /** 会话列表(父级持有并加载) */
  conversations: Conversation[]
  /** 当前选中会话ID(高亮) */
  currentId: string | null
}>()

const emit = defineEmits<{
  /** 选中会话(父级加载历史消息) */
  select: [id: string]
  /** 新建会话 */
  create: []
  /** 重命名会话 */
  rename: [conv: Conversation]
  /** 删除会话 */
  remove: [conv: Conversation]
}>()

// 侧栏开关(桌面默认展开, 移动端默认收起为抽屉; 状态由父级持有, 此处经 v-model 读写)
const open = defineModel<boolean>('open', { required: true })

const { hasPerm } = usePermission()

// 搜索关键字(侧栏本地视图状态)
const searchText = ref('')

/** 选中会话: 通知父级加载消息 */
const handleSelect = (id: string) => emit('select', id)

/** 新建会话 */
const handleCreate = () => emit('create')

// 次级管理入口(低调收纳于侧栏底部, 后续管理页在此追加一项即可)
const visibleManageLinks = computed(() => [
  { label: '知识库管理', icon: markRaw(Collection), index: '/rag/project', perm: 'rag:project' },
].filter((l) => !l.perm || hasPerm(l.perm)))

// 按日期分组会话(今天/昨天/7天内/更早), 支持标题搜索
const groupedConversations = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  const filtered = props.conversations.filter(
    (c) => !keyword || (c.title || '新对话').toLowerCase().includes(keyword),
  )
  const groups: { label: string; items: Conversation[] }[] = [
    { label: '今天', items: [] },
    { label: '昨天', items: [] },
    { label: '7 天内', items: [] },
    { label: '更早', items: [] },
  ]
  const now = Date.now()
  const startToday = new Date().setHours(0, 0, 0, 0)
  const startYesterday = startToday - 86400000
  const start7d = startToday - 7 * 86400000
  for (const conv of filtered) {
    const t = new Date(conv.updated_at || conv.created_at).getTime() || now
    if (t >= startToday) groups[0].items.push(conv)
    else if (t >= startYesterday) groups[1].items.push(conv)
    else if (t >= start7d) groups[2].items.push(conv)
    else groups[3].items.push(conv)
  }
  return groups.filter((g) => g.items.length > 0)
})
</script>

<style scoped>
/* 抽屉遮罩过渡 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
