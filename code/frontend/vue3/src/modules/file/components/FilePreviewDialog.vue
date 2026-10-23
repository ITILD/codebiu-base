<template>
  <!-- 在线预览对话框(REQ-016): 图片/PDF/Office/文本统一由 file-viewer 浏览器端渲染 -->
  <el-dialog v-model="visible" :title="title" width="86%" top="3vh" destroy-on-close append-to-body>
    <div v-loading="loading" h="70vh" min-h-60 overflow-hidden>
      <FileViewer
        v-if="previewFile"
        :file="previewFile"
        :options="{ theme: 'system', toolbar: { position: 'bottom-right' } }"
        @error="(msg: string) => ElMessage.error(`预览渲染失败: ${msg}`)"
      />
      <div v-else-if="loadError" h-full flex flex-col items-center justify-center text-note-sub>
        <el-icon text-4xl mb-3><WarningFilled /></el-icon>
        <p m-0>{{ loadError }}</p>
      </div>
    </div>
  </el-dialog>
</template>

<script lang="ts">
// 可预览扩展名白名单(preset-lite 文本/图片 + preset-office PDF/Office 覆盖的格式),
// 供列表页按钮显隐与对话框内部校验复用
import type { FileEntry } from '../types/file';

const PREVIEWABLE_EXTENSIONS = new Set([
  // 图片(preset-lite renderer-image)
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff', 'tif', 'avif',
  // PDF(preset-office renderer-pdf)
  'pdf',
  // Word(preset-office renderer-word)
  'docx', 'docm', 'doc', 'dot', 'rtf', 'odt',
  // Excel(preset-office renderer-spreadsheet)
  'xlsx', 'xlsm', 'xlsb', 'xls', 'csv', 'tsv',
  // PowerPoint(preset-office renderer-presentation; 不含 .ppt 二进制老格式,
  // 其渲染链路内置 16M CJK 字体, 收益低体积高, 老格式请转存 pptx)
  'pptx', 'pptm', 'ppsx',
  // 文本/代码/Markdown(preset-lite renderer-text)
  'txt', 'md', 'markdown', 'log', 'json', 'xml', 'yaml', 'yml', 'html', 'htm',
]);

/** 行是否可在线预览(目录与白名单外格式不支持) */
export const isFilePreviewable = (row: Pick<FileEntry, 'is_directory' | 'file_extension'>) => {
  if (row.is_directory) return false;
  return PREVIEWABLE_EXTENSIONS.has((row.file_extension || '').toLowerCase());
};
</script>

<script setup lang="ts">
// 文件在线预览对话框: authFetch 拉取内联预览流 -> File 对象交给 file-viewer
// (preset-lite 文本/图片 + preset-office PDF/Word/Excel/PPT 浏览器端解析, 零服务端转码)
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import FileViewer from '@file-viewer/vue3'
import '@file-viewer/vue3/dist/file-viewer3.css'
// 渲染器注册(vite 插件虚拟模块, vite.config.ts 中 inject:false): 静态引入使 6 个
// 渲染器 chunk 成为文件管理页懒加载分包的依赖, 首屏入口不再携带(~2.3MB)
import 'virtual:file-viewer-renderers'
import { authFetch } from '@/common/api/authFetch'
import { getFilePreviewPath } from '../api/filesystem'

/** 预览大小上限: 超过提示下载后查看(浏览器端解析大文件内存峰值高) */
const PREVIEW_MAX_BYTES = 50 * 1024 * 1024

const visible = ref(false)
const loading = ref(false)
const loadError = ref('')
const title = ref('')
const previewFile = ref<File | null>(null)

// 打开预览: 校验类型/权限/大小后拉取内联流
const open = async (row: FileEntry) => {
  if (!isFilePreviewable(row)) {
    ElMessage.warning('该文件类型暂不支持在线预览')
    return
  }
  if (!row.can_download) {
    ElMessage.warning('无下载权限，不可预览')
    return
  }
  if ((row.file_size_bytes ?? 0) > PREVIEW_MAX_BYTES) {
    ElMessage.warning('文件超过 50MB，请下载后查看')
    return
  }
  title.value = row.name
  loadError.value = ''
  previewFile.value = null
  visible.value = true
  loading.value = true
  try {
    const resp = await authFetch(getFilePreviewPath(row.id))
    if (!resp.ok) {
      const detail = await resp.json().catch(() => null)
      throw new Error(detail?.detail ?? `HTTP ${resp.status}`)
    }
    const blob = await resp.blob()
    previewFile.value = new File(
      [blob],
      row.name,
      { type: row.mime_type || blob.type || 'application/octet-stream' },
    )
  } catch (error) {
    console.error('预览加载失败:', error)
    loadError.value = '预览加载失败: ' + (error instanceof Error ? error.message : '未知错误')
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>
