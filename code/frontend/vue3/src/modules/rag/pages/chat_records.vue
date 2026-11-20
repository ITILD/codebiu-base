<!-- 对话记录页(系统管理员): 全站会话列表(token/成本聚合) + 消息查看 + 批量删除 -->
<template>
  <div p-3 md:p-4 w-full>
    <InkPageHead title="对话记录" sub="全站会话的 token 消耗与成本记录" seal="录" />

    <!-- 非管理员提示 -->
    <el-empty v-if="!isAdmin" description="对话记录仅系统管理员可访问" />

    <template v-else>
      <!-- 工具栏: 搜索 + 批量删除 -->
      <div mb-3 flex flex-wrap items-center gap-y-2>
        <el-input
          style="width: min(260px, 100%)"
          v-model="userFilter"
          placeholder="按用户ID过滤(可选)"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button :icon="Search" @click="handleSearch" />
          </template>
        </el-input>
        <div flex-1 />
        <el-button
          type="danger"
          plain
          :disabled="!selectedIds.length"
          :loading="batchDeleting"
          @click="handleBatchDelete"
        >
          批量删除{{ selectedIds.length ? `(${selectedIds.length})` : '' }}
        </el-button>
        <el-button :icon="Refresh" @click="fetchData">刷新</el-button>
      </div>

      <!-- 会话列表 -->
      <el-table
        :data="tableData"
        v-loading="loading"
        border
        stripe
        w-full
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column label="对话标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || '(未命名对话)' }}</template>
        </el-table-column>
        <el-table-column label="所属用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.nickname || row.username || row.user_id }}</template>
        </el-table-column>
        <el-table-column prop="rounds" label="轮次" width="70" align="center" />
        <el-table-column label="输入 token" width="110" align="right">
          <template #default="{ row }">{{ fmtTokens(row.prompt_tokens) }}</template>
        </el-table-column>
        <el-table-column label="输出 token" width="110" align="right">
          <template #default="{ row }">{{ fmtTokens(row.completion_tokens) }}</template>
        </el-table-column>
        <el-table-column label="合计" width="110" align="right">
          <template #default="{ row }">{{ fmtTokens(row.total_tokens) }}</template>
        </el-table-column>
        <el-table-column label="成本(元)" width="110" align="right">
          <template #default="{ row }">{{ fmtCost(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="最近活跃" width="170">
          <template #default="{ row }">{{ formatTimeShort(row.last_active_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" :fixed="isMd ? 'right' : false">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDrawer(row)">查看消息</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div mt-4 flex flex-wrap justify-center sm:justify-end>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchData"
          @current-change="fetchData"
        />
      </div>

      <!-- 对话消息抽屉 -->
      <el-drawer
        v-model="drawerVisible"
        :title="drawerTitle"
        :size="isMd ? '62%' : '100%'"
        destroy-on-close
      >
        <div v-loading="messagesLoading" class="h-full">
          <div v-if="currentRow" mb-3 text-sm text-note-sub>
            所属用户：{{ currentRow.nickname || currentRow.username || currentRow.user_id }}
            <span mx-2>·</span>{{ currentRow.rounds }} 轮
            <span mx-2>·</span>{{ fmtTokens(currentRow.total_tokens) }} tokens
            <span mx-2>·</span>{{ fmtCost(currentRow.cost) }} 元
          </div>

          <el-empty v-if="!messagesLoading && messages.length === 0" description="该对话暂无消息记录" />
          <el-table v-else :data="messages" border stripe size="small">
            <el-table-column label="角色" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="roleTagType(row.role)" size="small" effect="plain" round>
                  {{ roleLabel(row.role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="内容" :min-width="isMd ? 420 : 240">
              <template #default="{ row }">
                <div class="msg-content">{{ row.content }}</div>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatTimeShort(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-drawer>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Search, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import type { PaginationParams, PaginationResponse } from '@/common/types/common'
import { usePermission } from '@/common/composables/usePermission'
import { useResponsive } from '@/common/composables/useResponsive'
import { formatTimeShort } from '@/common/utils/datetime'
import { getUsageConversations } from '../api/usage'
import { deleteConversation, listConversationMessages } from '../api/conversation'
import type { UsageConversationItem } from '../types/usage'
import type { ChatMessage } from '../types'

// 对话记录管理仅系统管理员
const { isAdmin } = usePermission()
const { isMd } = useResponsive()
const route = useRoute()
const router = useRouter()

/** token/数量格式化(空数据显示 -) */
const fmtTokens = (value?: number | null) =>
  value == null ? '-' : Number(value).toLocaleString()

/** 成本格式化: 大额两位小数, 小额四位小数(避免精度丢失显示为 0) */
const fmtCost = (value?: number | null) =>
  value == null ? '-' : Number(value) >= 1 ? Number(value).toFixed(2) : Number(value).toFixed(4)

// ── 会话列表 ──
const userFilter = ref('')
const pagination = ref<PaginationParams>({ page: 1, size: 10 })
const tableData = ref<UsageConversationItem[]>([])
const total = ref(0)
const loading = ref(true)

// 批量选择与删除
const selectedIds = ref<string[]>([])
const batchDeleting = ref(false)

const handleSelectionChange = (rows: UsageConversationItem[]) => {
  selectedIds.value = rows.map((r) => r.conversation_id)
}

/** 批量删除会话(同时删除关联消息, 二次确认; 逐个调用删除接口) */
const handleBatchDelete = async () => {
  const count = selectedIds.value.length
  try {
    await ElMessageBox.confirm(
      `将删除 ${count} 个对话及其全部消息记录, 用量记录保留用于成本核算。是否继续?`,
      '批量删除对话',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    batchDeleting.value = true
    let failed = 0
    for (const id of selectedIds.value) {
      try {
        await deleteConversation(id)
      } catch {
        failed++
      }
    }
    if (failed > 0) {
      ElMessage.warning(`删除完成, ${failed} 个对话删除失败`)
    } else {
      ElMessage.success(`已删除 ${count} 个对话`)
    }
    selectedIds.value = []
    fetchData()
  } finally {
    batchDeleting.value = false
  }
}

const fetchData = async () => {
  try {
    loading.value = true
    const response: PaginationResponse<UsageConversationItem> = await getUsageConversations({
      ...pagination.value,
      user_id: userFilter.value || undefined,
    })
    tableData.value = response.items
    total.value = response.total
    // 从用量统计页跳转过来时自动打开对应会话
    const target = String(route.query.conversation_id || '')
    if (target) {
      const row = tableData.value.find((r) => r.conversation_id === target)
      if (row) openDrawer(row)
      router.replace({ query: { ...route.query, conversation_id: undefined } })
    }
    if (response.items.length === 0 && pagination.value.page > 1) {
      pagination.value.page -= 1
      await fetchData()
    }
  } catch (error) {
    console.error('获取对话记录失败:', error)
    ElMessage.error('获取对话记录失败，请重试')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.value.page = 1
  fetchData()
}

// ── 消息抽屉 ──
const drawerVisible = ref(false)
const messagesLoading = ref(false)
const currentRow = ref<UsageConversationItem | null>(null)
const messages = ref<ChatMessage[]>([])

const drawerTitle = computed(() =>
  currentRow.value ? `对话消息：${currentRow.value.title || '(未命名对话)'}` : '对话消息'
)

const roleLabel = (role: string) =>
  ({ user: '用户', assistant: 'AI 回答', system: '系统' })[role] || role

const roleTagType = (role: string): 'primary' | 'success' | 'info' =>
  ({ user: 'primary', assistant: 'success', system: 'info' } as const)[role as 'user'] || 'info'

const openDrawer = async (row: UsageConversationItem) => {
  currentRow.value = row
  messages.value = []
  drawerVisible.value = true
  try {
    messagesLoading.value = true
    const response: PaginationResponse<ChatMessage> = await listConversationMessages(
      row.conversation_id,
      { page: 1, size: 1000 }
    )
    messages.value = response.items
  } catch (error) {
    console.error('获取对话消息失败:', error)
    ElMessage.error('获取对话消息失败，请重试')
  } finally {
    messagesLoading.value = false
  }
}

onMounted(() => {
  if (isAdmin.value) fetchData()
})
</script>

<style scoped>
.msg-content {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
  line-height: 1.6;
}
</style>
