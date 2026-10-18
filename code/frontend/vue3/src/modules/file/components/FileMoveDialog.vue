<template>
  <!-- 移动条目对话框(目录树懒加载) -->
  <el-dialog v-model="dialogVisible" title="移动到指定目录" width="90%" class="max-w-[460px]">
    <el-alert
      v-if="moveEntryData"
      :title="`将移动「${moveEntryData.name}」${moveEntryData.is_directory ? '及其全部子项' : ''}到所选目录`"
      type="info"
      :closable="false"
      mb-3
    />
    <el-tree
      v-if="dialogVisible"
      ref="moveTreeRef"
      :data="moveTreeData"
      :props="treeProps"
      node-key="id"
      lazy
      highlight-current
      :load="loadTreeNodes"
      :expand-on-click-node="false"
      @node-click="handleTreeNodeClick"
      class="max-h-[320px] overflow-auto rounded bg-note-soft"
    >
      <template #default="{ node, data }">
        <span flex items-center gap-1>
          <el-icon text-amber-500><Folder /></el-icon>
          <span>{{ node.label }}</span>
          <el-tag v-if="data.is_root" size="small" type="success" effect="plain">根目录</el-tag>
        </span>
      </template>
    </el-tree>
    <template #footer>
      <span>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMoveSubmit" :loading="submitting">
          移动到「{{ moveTargetName || '根目录' }}」
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Folder } from '@element-plus/icons-vue'
import { ElMessage, type TreeInstance } from 'element-plus'
import { listDirs, moveEntry } from '../api/filesystem'
import type { FileEntry } from '../types/file'

// 移动成功后通知父级刷新列表
const emit = defineEmits<{ changed: [] }>()

// 目录树节点
type TreeNode = {
  id: string
  name: string
  is_root?: boolean
  leaf?: boolean
}

const dialogVisible = ref(false)
const moveTreeRef = ref<TreeInstance>()
// 待移动条目
const moveEntryData = ref<FileEntry | null>(null)
// 目录树数据(根目录为虚拟节点)
const moveTreeData = ref<TreeNode[]>([])
// 选中的目标目录ID(undefined 表示根目录)
const moveTargetPid = ref<string | undefined>(undefined)
// 选中的目标目录名(展示用)
const moveTargetName = ref('')
// 提交中
const submitting = ref(false)

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: 'leaf',
}

/** 打开移动对话框(重置目录树并默认选中根目录) */
const open = async (row: FileEntry) => {
  moveEntryData.value = row
  moveTargetPid.value = undefined
  moveTargetName.value = '根目录'
  moveTreeData.value = [
    { id: '__root__', name: '根目录', is_root: true, leaf: false },
  ]
  dialogVisible.value = true
  // 树渲染完成后展开并选中根目录节点
  await nextTick()
  moveTreeRef.value?.setCurrentKey('__root__')
  moveTreeRef.value?.getNode('__root__')?.expand()
}

/** 懒加载目录树节点(根目录虚拟节点加载根级子目录) */
// 参数类型与 el-tree 的 load 签名保持宽松兼容(node.data 为动态数据)
const loadTreeNodes = async (
  node: { data: Record<string, any> },
  resolve: (children: any[]) => void
) => {
  try {
    // 根目录虚拟节点 → 查询根级目录;其他节点按 id 查询子目录
    const pid = node.data.is_root ? undefined : node.data.id
    const dirs = await listDirs(pid)
    resolve(
      dirs.map((d) => ({
        id: d.id,
        name: d.name,
        leaf: false,
      }))
    )
  } catch (error) {
    console.error('加载目录树失败:', error)
    ElMessage.error('加载目录树失败')
    resolve([])
  }
}

/** 树节点点击选中目标目录(更新移动目标) */
const handleTreeNodeClick = (data: TreeNode) => {
  // 防护: 不可移动到条目自身(后端还有子孙环形引用校验)
  if (moveEntryData.value && data.id === moveEntryData.value.id) {
    ElMessage.warning('不能移动到自身目录')
    return
  }
  moveTargetPid.value = data.is_root ? undefined : data.id
  moveTargetName.value = data.name
}

/** 提交移动(使用点击选中的目标目录) */
const handleMoveSubmit = async () => {
  if (!moveEntryData.value) return
  try {
    submitting.value = true
    await moveEntry(moveEntryData.value.id, moveTargetPid.value)
    ElMessage.success(`已移动到「${moveTargetName.value || '根目录'}」`)
    dialogVisible.value = false
    emit('changed')
  } catch (error) {
    console.error('移动失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '移动失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>
