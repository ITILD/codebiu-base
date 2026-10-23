<template>
  <div p-2 w-full flex flex-col h-app>
    <!-- 工具栏 -->
    <div mb-3 flex flex-wrap items-center gap-2>
      <el-tooltip content="返回上级" placement="top">
        <el-button :icon="Back" :disabled="!currentPid" @click="handleUp" />
      </el-tooltip>
      <el-breadcrumb separator="/" flex-1 min-w-0>
        <el-breadcrumb-item>
          <span cursor-pointer hover:text-note-green @click="handleGoto(-1)">根目录</span>
        </el-breadcrumb-item>
        <el-breadcrumb-item v-for="(crumb, idx) in breadcrumbs" :key="crumb.id">
          <span cursor-pointer hover:text-note-green @click="handleGoto(idx)">{{ crumb.name }}</span>
        </el-breadcrumb-item>
      </el-breadcrumb>
      <el-input
        class="w-full sm:w-56"
        v-model="searchQuery"
        placeholder="按名称搜索"
        clearable
        :prefix-icon="Search"
        @input="handleSearchDebounced"
        @clear="handleSearchDebounced"
      />
      <el-button :icon="FolderAdd" @click="handleCreateFolder" :disabled="loading">新建目录</el-button>
      <el-button type="danger" plain :icon="Delete" :disabled="!selectedEntries.length" @click="handleBatchDelete">
        批量删除{{ selectedEntries.length ? `(${selectedEntries.length})` : '' }}
      </el-button>
      <el-upload :show-file-list="false" :before-upload="handleUpload" :disabled="uploading" multiple>
        <el-button type="primary" :loading="uploading" :icon="Upload">
          {{ uploading ? '上传中' : '上传文件' }}
        </el-button>
      </el-upload>
    </div>

    <!-- 目录内容表格 -->
    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="entries"
      stripe
      flex-1
      @row-dblclick="handleOpen"
      @selection-change="handleSelectionChange"
    >
      <!-- 业务条目(rag/avatar等)由各业务模块自管, 禁止勾选批量删除 -->
      <el-table-column type="selection" width="42" :selectable="(row: FileEntry) => !isBusinessEntry(row)" />
      <el-table-column label="名称" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">
          <div flex items-center gap-2 cursor-pointer @click="handleOpen(row)">
            <el-icon text-lg :class="row.is_directory ? 'text-amber-500' : fileIconClass(row.file_extension)">
              <Folder v-if="row.is_directory" />
              <Document v-else />
            </el-icon>
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_directory" size="small" type="warning" effect="plain">目录</el-tag>
            <!-- 来源模块标记: 业务条目(rag/avatar等)在虚拟树中独立成模块大文件夹 -->
            <el-tag v-if="sourceLabel(row)" size="small" type="success" effect="plain">
              {{ sourceLabel(row) }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="大小" min-width="110" align="center">
        <template #default="{ row }">
          {{ row.is_directory ? '-' : formatSize(row.file_size_bytes) }}
        </template>
      </el-table-column>
      <el-table-column label="类型" min-width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="!row.is_directory" size="small" type="info">
            {{ (row.file_extension || 'file').toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="标签" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.tags && row.tags.length">
            <el-tag v-for="t in row.tags.slice(0, 2)" :key="t" size="small" effect="plain" mr-1>{{ t }}</el-tag>
            <span v-if="row.tags.length > 2" text-note-sub text-xs>+{{ row.tags.length - 2 }}</span>
          </template>
          <span v-else text-note-sub>-</span>
        </template>
      </el-table-column>
      <el-table-column label="描述" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.description || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="修改时间" min-width="120" align="center">
        <template #default="{ row }">
          {{ formatDate(row.updated_at) }}
        </template>
      </el-table-column>
      <!-- 操作列: 平板及以上固定右侧, 手机取消固定避免遮挡(表格自带横向滚动);
           业务条目(rag/avatar等)只读, 仅保留详情/下载; 下载为独立权限, 无权限按钮灰显 -->
      <el-table-column label="操作" min-width="320" align="center" :fixed="isMd ? 'right' : false">
        <template #default="{ row }">
          <el-button size="small" plain @click="handleShowDetail(row)">详情</el-button>
          <el-tooltip v-if="!row.is_directory && isFilePreviewable(row)" :disabled="row.can_download"
            content="无下载权限，不可预览" placement="top">
            <el-button size="small" plain :disabled="!row.can_download" @click="handlePreview(row)">
              预览
            </el-button>
          </el-tooltip>
          <template v-if="!isBusinessEntry(row)">
            <el-tooltip v-if="!row.is_directory" :disabled="row.can_download"
              content="无下载权限(需管理员配置)" placement="top">
              <el-button size="small" type="primary" plain :disabled="!row.can_download"
                @click="handleDownload(row)">
                下载
              </el-button>
            </el-tooltip>
            <el-button size="small" type="success" plain @click="handleMove(row)">移动</el-button>
            <el-button size="small" type="warning" plain @click="handleEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
          </template>
          <el-tooltip v-else-if="!row.is_directory" :disabled="row.can_download"
            content="无下载权限(需项目编辑者及以上档位或管理员配置)" placement="top">
            <el-button size="small" type="primary" plain :disabled="!row.can_download"
              @click="handleDownload(row)">
              下载
            </el-button>
          </el-tooltip>
          <span v-else text-note-sub text-xs>业务模块管理</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态提示 -->
    <div v-if="!loading && entries.length === 0" py-10 flex flex-col items-center text-note-sub>
      <el-icon text-5xl mb-3><FolderOpened /></el-icon>
      <p m-0>{{ searchQuery ? '未找到匹配的条目' : '当前目录为空，可上传文件或新建目录' }}</p>
    </div>

    <!-- 分页(手机居中, 桌面靠右) -->
    <div mt-3 flex flex-wrap justify-center sm:justify-end>
      <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
        :total="total" layout="total, prev, pager, next"
        @size-change="fetchData" @current-change="fetchData" />
    </div>

    <!-- 新建目录对话框(子组件自持状态, open 时重置) -->
    <FolderDialog ref="folderDialogRef" :pid="currentPid" @saved="fetchData" />

    <!-- 编辑条目对话框(子组件 open(row) 回填) -->
    <FileEditDialog ref="fileEditDialogRef" @saved="fetchData" />

    <!-- 移动条目对话框(子组件目录树懒加载选择) -->
    <FileMoveDialog ref="fileMoveDialogRef" @changed="fetchData" />

    <!-- 条目详情抽屉(子组件 open(row) 拉取详情) -->
    <FileDetailDrawer ref="fileDetailDrawerRef" :source-label="sourceLabel" :format-size="formatSize" />

    <!-- 在线预览对话框(file-viewer 浏览器端渲染, 子组件 open(row) 校验并拉流) -->
    <FilePreviewDialog ref="filePreviewRef" />
  </div>
</template>

<script setup lang="ts">
import {
  Back,
  Upload,
  FolderAdd,
  Folder,
  Document,
  FolderOpened,
  Search,
  Delete,
} from '@element-plus/icons-vue'
import {
  listDir,
  uploadFile,
  getFileDownloadUrl,
  deleteFile,
  deleteFolder,
  batchDeleteEntries,
  checkDownloadPerms,
} from '../api/filesystem'
import type { FileEntry } from '../types/file'
import { ElMessage, ElMessageBox, type TableInstance } from 'element-plus'
import { useResponsive } from '@/common/composables/useResponsive'
import { usePermission } from '@/common/composables/usePermission'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { formatDate } from '@/common/utils/datetime'
import FolderDialog from '../components/FolderDialog.vue'
import FileEditDialog from '../components/FileEditDialog.vue'
import FileMoveDialog from '../components/FileMoveDialog.vue'
import FileDetailDrawer from '../components/FileDetailDrawer.vue'
import FilePreviewDialog, { isFilePreviewable } from '../components/FilePreviewDialog.vue'

// 屏幕档位: 操作列在平板及以上才固定右侧
const { isMd } = useResponsive()
// 全局下载权限(main:file:download, 管理员穿透): 持有者无需逐条探测
const { hasPerm } = usePermission()

// 面包屑目录栈(从根到当前目录)
const breadcrumbs = ref<{ id: string; name: string }[]>([])
// 当前目录ID(空表示根目录)
const currentPid = computed(() =>
  breadcrumbs.value.length ? breadcrumbs.value[breadcrumbs.value.length - 1].id : undefined
)

// 上传/搜索状态(列表数据统一由 useTableQuery 管理)
const uploading = ref(false)
const searchQuery = ref('')

// 多选条目(批量删除用)
const tableRef = ref<TableInstance>()
const selectedEntries = ref<FileEntry[]>([])
const handleSelectionChange = (rows: FileEntry[]) => {
  selectedEntries.value = rows
}

// 文件图标按扩展名着色
const fileIconClass = (ext: string) => {
  const e = (ext || '').toLowerCase()
  if (['pdf'].includes(e)) return 'text-red-500'
  if (['doc', 'docx'].includes(e)) return 'text-blue-500'
  if (['xls', 'xlsx', 'csv'].includes(e)) return 'text-green-500'
  if (['ppt', 'pptx'].includes(e)) return 'text-orange-500'
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(e)) return 'text-purple-500'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(e)) return 'text-yellow-500'
  return 'text-note-sub'
}

// 业务来源模块的展示名(NULL/'file' 表示文件管理自有条目)
const SOURCE_MODULE_LABELS: Record<string, string> = {
  rag: '知识库',
  avatar: '用户头像',
}
const sourceLabel = (row: FileEntry) =>
  row.source_module && row.source_module !== 'file'
    ? SOURCE_MODULE_LABELS[row.source_module] || row.source_module
    : ''
// 业务条目只读(移动/编辑/删除入口隐藏, 由对应业务模块管理)
const isBusinessEntry = (row: FileEntry) => !!sourceLabel(row)

// 文件大小格式化(null/0 显示 '-')
const formatSize = (bytes: number | null | undefined) => {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

// 日期/日期时间格式化: 统一使用 @/common/utils/datetime (formatDate/formatDateTime)

// 回填行级下载权限(下载独立于浏览: 持全局权限直接激活, 否则批量探测,
// 后端口径与下载接口一致: main:file:download / avatar 公开 / rag 项目档位)
const fillDownloadPerms = async (items: FileEntry[]) => {
  const fileRows = items.filter((e) => !e.is_directory)
  if (!fileRows.length) return
  if (hasPerm('main:file:download')) {
    fileRows.forEach((e) => {
      e.can_download = true
    })
    return
  }
  try {
    const perms = await checkDownloadPerms(fileRows.map((e) => e.id))
    fileRows.forEach((e) => {
      e.can_download = !!perms[e.id]
    })
  } catch (error) {
    console.error('探测下载权限失败:', error)
    fileRows.forEach((e) => {
      e.can_download = false
    })
  }
}

// 目录内容列表: 分页/拉取/末页空页回退统一收口(useTableQuery)
const {
  pagination, tableData: entries, total, loading, fetchData, refreshAfterRemove,
} = useTableQuery<FileEntry>(async (params) => {
  // 服务端按名称过滤(空值不传)
  return listDir(currentPid.value, params, searchQuery.value.trim() || undefined)
}, {
  // 拉取成功后的副作用: 回填行级下载权限并清空多选
  afterFetch: async (items) => {
    await fillDownloadPerms(items)
    // 数据刷新后清空多选状态
    tableRef.value?.clearSelection()
    selectedEntries.value = []
  },
  errorMsg: '获取目录内容失败',
})
// 目录页默认每页 50 条
pagination.value.size = 50

// 搜索防抖(300ms)
let searchTimer: ReturnType<typeof setTimeout> | undefined
const handleSearchDebounced = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    pagination.value.page = 1
    fetchData()
  }, 300)
}

// 打开条目(目录进入; 文件有权限且支持预览时直接预览)
const handleOpen = (row: FileEntry) => {
  if (!row.is_directory) {
    if (row.can_download && isFilePreviewable(row)) handlePreview(row)
    return
  }
  breadcrumbs.value.push({ id: row.id, name: row.name })
  pagination.value.page = 1
  fetchData()
}

// 面包屑跳转(-1 表示根目录)
const handleGoto = (idx: number) => {
  breadcrumbs.value = breadcrumbs.value.slice(0, idx + 1)
  pagination.value.page = 1
  fetchData()
}

// 返回上级目录
const handleUp = () => {
  if (!breadcrumbs.value.length) return
  breadcrumbs.value.pop()
  pagination.value.page = 1
  fetchData()
}

// 上传文件(返回 false 阻止 el-upload 默认行为)
const handleUpload = async (file: File) => {
  try {
    uploading.value = true
    await uploadFile(file, currentPid.value)
    ElMessage.success(`文件"${file.name}"上传成功`)
    fetchData()
  } catch (error) {
    console.error('上传失败:', error)
    ElMessage.error(`文件"${file.name}"上传失败`)
  } finally {
    uploading.value = false
  }
  return false
}

// 下载文件(新窗口触发后端下载流; 无权限时按钮已灰显, 此处兜底拦截)
const handleDownload = (row: FileEntry) => {
  if (!row.can_download) return
  window.open(getFileDownloadUrl(row.id), '_blank')
}

// ---------------- 对话框/抽屉子组件编排(状态自持, open 时重置防脏数据) ----------------
const folderDialogRef = ref<InstanceType<typeof FolderDialog>>()
const fileEditDialogRef = ref<InstanceType<typeof FileEditDialog>>()
const fileMoveDialogRef = ref<InstanceType<typeof FileMoveDialog>>()
const fileDetailDrawerRef = ref<InstanceType<typeof FileDetailDrawer>>()
const filePreviewRef = ref<InstanceType<typeof FilePreviewDialog>>()

// 打开新建目录对话框
const handleCreateFolder = () => folderDialogRef.value?.open()

// 打开编辑对话框(子组件回填行数据)
const handleEdit = (row: FileEntry) => fileEditDialogRef.value?.open(row)

// 打开在线预览(类型/权限/大小校验在子组件 open 内)
const handlePreview = (row: FileEntry) => filePreviewRef.value?.open(row)

// ---------------- 批量删除 ----------------
const handleBatchDelete = async () => {
  // 双保险过滤: 业务条目不可批量删除(由各业务模块自管), 勾选框已禁用
  const rows = selectedEntries.value.filter((r) => !isBusinessEntry(r))
  if (!rows.length) return
  const folderCount = rows.filter((r) => r.is_directory).length
  const tip = folderCount
    ? `确定删除选中的 ${rows.length} 项吗？其中包含 ${folderCount} 个目录，目录下全部内容将一并删除。`
    : `确定删除选中的 ${rows.length} 项吗？`
  try {
    await ElMessageBox.confirm(tip, '批量删除', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    const res = await batchDeleteEntries(rows.map((r) => r.id))
    if (res.failed.length) {
      ElMessage.warning(`成功删除 ${res.deleted} 项，${res.failed.length} 项失败`)
    } else {
      ElMessage.success(`成功删除 ${res.deleted} 项`)
    }
    // 删除后刷新(末行回退翻页统一由 useTableQuery 处理)
    refreshAfterRemove(res.deleted)
  } catch (error) {
    console.log('取消批量删除或删除失败:', error)
  }
}

// 打开详情抽屉(子组件拉取最新详情)
const handleShowDetail = (row: FileEntry) => fileDetailDrawerRef.value?.open(row)

// 打开移动对话框(子组件重置目录树并默认选中根目录)
const handleMove = (row: FileEntry) => fileMoveDialogRef.value?.open(row)

// 删除条目(目录递归删除)
const handleDelete = async (row: FileEntry) => {
  try {
    await ElMessageBox.confirm(
      row.is_directory
        ? `确定删除目录"${row.name}"吗？目录下全部内容将一并删除。`
        : `确定删除文件"${row.name}"吗？`,
      '警告',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
    if (row.is_directory) {
      await deleteFolder(row.id)
    } else {
      await deleteFile(row.id)
    }
    ElMessage.success('删除成功')
    // 删除后刷新(末行回退翻页统一由 useTableQuery 处理)
    refreshAfterRemove()
  } catch (error) {
    console.log('取消删除或删除失败:', error)
  }
}
</script>
