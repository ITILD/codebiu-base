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
          @search="handleSearchWithRange"
          @reset="handleSearchWithRange"
        />
        <el-date-picker
          v-model="timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          size="default"
          aria-label="时间范围"
          class="max-w-[340px]"
        />
        <el-button type="primary" @click="handleSearchWithRange">查询</el-button>
      </div>

      <!-- 审计列表: ProTable 统一承载列设置/密度/移动端卡片(只读页, 不开批量与行内编辑) -->
      <ProTable
        :columns="columns"
        :data="tableData"
        :loading="loading"
        table-key="main-audit"
        card-title-prop="path"
        :skeleton-rows="4"
      >
        <template #toolbar>
          <span text-sm text-note-sub>{{ t('pt_total', { n: total }) }}</span>
        </template>

        <!-- 操作人: 未登录请求展示"匿名"标签 -->
        <template #col-username="{ row }">
          <span v-if="row.username">{{ row.username }}</span>
          <el-tag v-else size="small" type="info">匿名</el-tag>
        </template>

        <!-- 方法: 语义色标签 -->
        <template #col-method="{ row }">
          <el-tag :type="methodTagType(row.method)" size="small">{{ row.method }}</el-tag>
        </template>

        <!-- 状态码: <400 成功, 否则失败 -->
        <template #col-status_code="{ row }">
          <el-tag :type="row.status_code < 400 ? 'success' : 'danger'" size="small">
            {{ row.status_code }}
          </el-tag>
        </template>

        <!-- 详情: 参数摘要/User-Agent 全文(替代原展开行) -->
        <template #row-actions="{ row }">
          <el-popover placement="left" trigger="click" :width="320">
            <template #reference>
              <el-button link type="primary" size="small" :aria-label="`查看详情 ${row.path}`">
                详情
              </el-button>
            </template>
            <div class="max-h-[40vh] overflow-y-auto text-xs break-all">
              <p mb-1><b>参数摘要：</b>{{ row.params_digest ?? '—' }}</p>
              <p text-note-sub><b>User-Agent：</b>{{ row.user_agent ?? '—' }}</p>
            </div>
          </el-popover>
        </template>
      </ProTable>

      <!-- 分页 -->
      <div mt-3 flex justify-center>
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
          :total="total" layout="total, prev, pager, next" small
          @size-change="fetchData" @current-change="fetchData" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { listAuditLogs } from '../api/audit'
import type { AuditLog } from '../types/audit'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import ProTable from '@/common/components/pro-table/ProTable.vue'
import type { ProTableColumn } from '@/common/components/pro-table/useProTablePrefs'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { formatDateTime } from '@/common/utils/datetime'
import { i18n } from '@/common/i18n/language'
import type { PaginationParams } from '@/common/types/common'

// 系统三语(中/英/日): 词条统一经 i18n.global.t 获取
const { t } = i18n.global

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
// 时间范围(Date 对象, 提交时转 ISO)
const timeRange = ref<[Date, Date] | null>(null)

// 列配置: 只读列表, 语义列(操作人/方法/状态)走动态插槽, 时间/耗时走 formatter
const columns: ProTableColumn[] = [
  {
    prop: 'created_at', label: '时间', minWidth: 150,
    formatter: (row) => formatDateTime(row.created_at as string),
  },
  { prop: 'username', label: '操作人', minWidth: 110, slot: true },
  { prop: 'method', label: '方法', minWidth: 76, align: 'center', slot: true },
  { prop: 'path', label: '路径', minWidth: 200, showOverLimit: true },
  { prop: 'status_code', label: '状态', minWidth: 76, align: 'center', slot: true },
  {
    prop: 'duration_ms', label: '耗时', minWidth: 86, align: 'right',
    formatter: (row) => (row.duration_ms == null ? '' : `${row.duration_ms as number}ms`),
  },
  { prop: 'ip', label: 'IP', minWidth: 120, showOverLimit: true },
  { prop: 'params_digest', label: '参数摘要', minWidth: 200, showOverLimit: true },
]

/** 方法标签色: 删除红/新增蓝/修改橙 */
const methodTagType = (method: string) => {
  if (method === 'DELETE') return 'danger'
  if (method === 'POST') return 'primary'
  if (method === 'PUT' || method === 'PATCH') return 'warning'
  return 'info'
}

/** 列表接口适配: 清空空串过滤条件, 避免无意义查询参数 */
const fetchAuditLogs = (params: PaginationParams & Record<string, unknown>) =>
  listAuditLogs({
    page: params.page,
    size: params.size,
    keyword: (params.keyword as string) || undefined,
    username: (params.username as string) || undefined,
    method: (params.method as string) || undefined,
    start: (params.start as string) || undefined,
    end: (params.end as string) || undefined,
  })

// 分页/查询/数据/loading 统一复用 useTableQuery
const { pagination, queryParams, tableData, total, loading, fetchData, handleSearch } =
  useTableQuery<AuditLog>(fetchAuditLogs, {
    errorMsg: '获取审计日志失败',
    defaultQuery: {
      keyword: '',
      username: '',
      method: undefined,
      start: undefined,
      end: undefined,
    },
  })
// 审计日志每页 20 条(与改造前一致)
pagination.value.size = 20

/** 搜索/重置: 时间范围转 ISO 写入查询参数后回到第一页重新查询 */
const handleSearchWithRange = () => {
  queryParams.value = {
    ...queryParams.value,
    start: timeRange.value?.[0]?.toISOString(),
    end: timeRange.value?.[1]?.toISOString(),
  }
  handleSearch()
}
</script>
