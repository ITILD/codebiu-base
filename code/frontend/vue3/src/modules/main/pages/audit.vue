<template>
  <div p-4 md:p-6 w-full class="audit-page">
    <!-- 水墨页头 -->
    <InkPageHead title="操作审计" seal="察">
      <template #sub>
        写操作与登录登出全量留痕，敏感参数已脱敏
      </template>
    </InkPageHead>

    <div page-card>
      <!-- 过滤栏: 关键字/用户名/方法 + 时间范围 -->
      <div mb-3 flex flex-wrap items-center gap-2>
        <TableSearchBar
          v-model="queryParams"
          :fields="searchFields"
          :collapse-count="3"
          @search="handleSearch"
          @reset="handleSearch"
        />
        <el-date-picker
          v-model="timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          size="default"
          class="max-w-[340px]"
        />
        <el-button type="primary" @click="handleSearch">查询</el-button>
      </div>

      <!-- 审计表格 -->
      <el-table :data="logList" v-loading="loading" stripe size="small">
        <el-table-column label="时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.username">{{ row.username }}</span>
            <el-tag v-else size="small" type="info">匿名</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="方法" min-width="76" align="center">
          <template #default="{ row }">
            <el-tag :type="methodTagType(row.method)" size="small">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="路径" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" min-width="76" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status_code < 400 ? 'success' : 'danger'" size="small">
              {{ row.status_code }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" min-width="86" align="right">
          <template #default="{ row }">{{ row.duration_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="ip" label="IP" min-width="120" show-overflow-tooltip />
        <el-table-column prop="params_digest" label="参数摘要" min-width="220" show-overflow-tooltip />
        <!-- 详情展开: 参数摘要/User-Agent 全文 -->
        <el-table-column type="expand" min-width="40">
          <template #default="{ row }">
            <div px-4 py-2 text-sm class="break-all">
              <p mb-1><b>参数摘要：</b>{{ row.params_digest ?? '—' }}</p>
              <p text-note><b>User-Agent：</b>{{ row.user_agent ?? '—' }}</p>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div mt-3 flex justify-center>
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
          :total="total" layout="total, prev, pager, next" small
          @size-change="fetchLogs" @current-change="fetchLogs" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { listAuditLogs } from '../api/audit'
import type { AuditLog } from '../types/audit'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import { formatDateTime } from '@/common/utils/datetime'
import type { PaginationParams } from '@/common/types/common'

// 过滤字段(路径关键字/用户名/方法)
const searchFields: SearchField[] = [
  { prop: 'keyword', label: '路径', placeholder: '请求路径模糊搜索' },
  { prop: 'username', label: '操作人', placeholder: '用户名模糊搜索' },
  {
    prop: 'method', label: '方法', type: 'select', options: [
      { label: 'POST', value: 'POST' },
      { label: 'PUT', value: 'PUT' },
      { label: 'DELETE', value: 'DELETE' },
      { label: 'PATCH', value: 'PATCH' },
    ]
  },
]
const queryParams = ref<Record<string, unknown>>({
  keyword: '',
  username: '',
  method: undefined,
})
// 时间范围(Date 对象, 提交时转 ISO)
const timeRange = ref<[Date, Date] | null>(null)

const loading = ref(false)
const logList = ref<AuditLog[]>([])
const total = ref(0)
const pagination = ref<PaginationParams>({ page: 1, size: 20 })

/** 方法标签色: 删除红/新增蓝/修改橙 */
const methodTagType = (method: string) => {
  if (method === 'DELETE') return 'danger'
  if (method === 'POST') return 'primary'
  if (method === 'PUT' || method === 'PATCH') return 'warning'
  return 'info'
}

/** 拉取审计日志列表(携带全部过滤条件) */
const fetchLogs = async () => {
  try {
    loading.value = true
    const { keyword, username, method } = queryParams.value
    const res = await listAuditLogs({
      ...pagination.value,
      keyword: (keyword as string) || undefined,
      username: (username as string) || undefined,
      method: (method as string) || undefined,
      start: timeRange.value?.[0]?.toISOString(),
      end: timeRange.value?.[1]?.toISOString(),
    })
    logList.value = res.items
    total.value = res.total
  } catch (error) {
    console.error('获取审计日志失败:', error)
    ElMessage.error('获取审计日志失败')
  } finally {
    loading.value = false
  }
}

/** 搜索/重置: 回到第一页后重新查询 */
const handleSearch = () => {
  pagination.value.page = 1
  fetchLogs()
}

onMounted(() => {
  fetchLogs()
})
</script>
