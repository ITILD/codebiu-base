<template>
  <!-- 条目详情抽屉(元数据/物理存储/上传用户/标签等) -->
  <el-drawer v-model="visible" title="条目详情" size="420px" class="max-w-[92vw]">
    <div v-loading="loading">
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
        <el-descriptions-item label="类型">
          {{ detail.is_directory ? '目录' : '文件' }}
          <el-tag v-if="sourceLabel(detail)" size="small" type="success" effect="plain" ml-1>
            {{ sourceLabel(detail) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item v-if="!detail.is_directory" label="大小">
          {{ formatSize(detail.file_size_bytes) }}
        </el-descriptions-item>
        <el-descriptions-item label="逻辑路径">{{ detail.logical_path }}</el-descriptions-item>
        <el-descriptions-item label="上传用户">{{ detail.owner_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatDateTime(detail.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="标签">
          <template v-if="detail.tags && detail.tags.length">
            <el-tag v-for="t in detail.tags" :key="t" size="small" effect="plain" mr-1>{{ t }}</el-tag>
          </template>
          <span v-else text-note-sub>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="描述">{{ detail.description || '-' }}</el-descriptions-item>
        <!-- 以下为文件专属内容元数据 -->
        <template v-if="!detail.is_directory">
          <el-descriptions-item label="扩展名">{{ detail.file_extension || '-' }}</el-descriptions-item>
          <el-descriptions-item label="MIME">{{ detail.mime_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="存储类型">{{ detail.storage_type || '-' }}</el-descriptions-item>
          <el-descriptions-item label="内容状态">{{ detail.content_status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="引用计数">{{ detail.ref_count ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="内容哈希">
            <span break-all text-xs font-mono>{{ detail.content_hash || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="物理存储位置">
            <span break-all text-xs font-mono>{{ detail.physical_storage || '-' }}</span>
          </el-descriptions-item>
        </template>
      </el-descriptions>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { getFileEntryDetail } from '../api/filesystem'
import type { FileEntry, FileEntryDetail } from '../types/file'
import { formatDateTime } from '@/common/utils/datetime'

// 展示辅助由父级传入(来源模块标签/文件大小格式化, 与列表表格保持单一来源)
defineProps<{
  /** 来源模块展示名(业务条目标记, 空串表示文件管理自有条目) */
  sourceLabel: (row: FileEntry) => string
  /** 文件大小格式化(null/0 显示 '-') */
  formatSize: (bytes: number | null | undefined) => string
}>()

const visible = ref(false)
const loading = ref(false)
// 条目详情(打开时拉取最新)
const detail = ref<FileEntryDetail | null>(null)

/** 打开详情抽屉(拉取最新元数据) */
const open = async (row: FileEntry) => {
  detail.value = null
  visible.value = true
  loading.value = true
  try {
    detail.value = await getFileEntryDetail(row.id)
  } catch (error) {
    console.error('获取详情失败:', error)
    ElMessage.error('获取详情失败')
    visible.value = false
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>
