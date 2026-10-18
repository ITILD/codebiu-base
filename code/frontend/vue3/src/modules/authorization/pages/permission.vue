<template>
  <div p-4 md:p-6 w-full>
    <!-- 水墨页头 -->
    <InkPageHead title="权限管理" sub="菜单与接口权限登记, 细粒度守门" seal="衡" />

    <!-- 统一搜索栏: 多字段筛选(名称/类型/状态, 客户端过滤树) -->
    <TableSearchBar
      v-model="queryParams"
      :fields="searchFields"
      :collapse-count="3"
      @search="handleSearch"
      @reset="handleSearch"
    >
      <template #actions>
        <el-button type="primary" @click="handleCreate">
          新增权限
        </el-button>
      </template>
    </TableSearchBar>

    <!-- 树形数据表格(默认不展开, 点击箭头逐级展开) -->
    <el-table :data="filteredTree" v-loading="loading" stripe w-full row-key="id"
      :tree-props="{ children: 'children' }">
      <el-table-column prop="name" label="菜单名称" min-width="180" />
      <el-table-column prop="menu_type" label="菜单类型" min-width="100">
        <template #default="{ row }">
          <el-tag :type="menuTypeTagType(row.menu_type)">{{ menuTypeLabel(row.menu_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="perms" label="权限标识" min-width="160" />
      <el-table-column prop="code" label="权限代码" min-width="140" />
      <el-table-column prop="path" label="路由路径" min-width="140" />
      <el-table-column prop="component" label="组件路径" min-width="160" />
      <el-table-column prop="order_num" label="排序" min-width="80" />
      <el-table-column prop="visible" label="可见" min-width="80">
        <template #default="{ row }">
          <el-switch v-model="row.visible" disabled />
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" min-width="80">
        <template #default="{ row }">
          <el-switch v-model="row.is_active" disabled />
        </template>
      </el-table-column>
      <!-- 操作列: 平板及以上固定右侧, 手机取消固定避免遮挡 -->
      <el-table-column label="操作" min-width="220" :fixed="isMd ? 'right' : false">
        <template #default="{ row }">
          <el-button size="small" type="primary" plain @click="handleEdit(row)">编辑</el-button>
          <el-button size="small" type="success" plain @click="handleAddChild(row)">新增子项</el-button>
          <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑/创建对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="90%" class="max-w-[600px]">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="上级菜单" prop="parent_id">
          <el-tree-select v-model="form.parent_id" :data="parentTreeData"
            :props="{ label: 'name', children: 'children' }" node-key="id" check-strictly
            placeholder="请选择上级菜单" w-full />
        </el-form-item>
        <el-form-item label="菜单类型" prop="menu_type">
          <el-radio-group v-model="form.menu_type">
            <el-radio v-for="item in menuTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="菜单名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入菜单名称" />
        </el-form-item>
        <el-form-item label="权限代码" prop="code">
          <el-input v-model="form.code" placeholder="请输入权限代码" />
        </el-form-item>
        <el-form-item label="权限标识" prop="perms">
          <el-input v-model="form.perms" placeholder="如：system:user:list" />
        </el-form-item>
        <el-form-item v-if="form.menu_type === 'M' || form.menu_type === 'C'" label="路由路径" prop="path">
          <el-input v-model="form.path" placeholder="请输入路由路径" />
        </el-form-item>
        <el-form-item v-if="form.menu_type === 'C'" label="组件路径" prop="component">
          <el-input v-model="form.component" placeholder="请输入组件路径" />
        </el-form-item>
        <el-form-item label="图标" prop="icon">
          <el-input v-model="form.icon" placeholder="请输入图标" />
        </el-form-item>
        <el-form-item label="显示排序" prop="order_num">
          <el-input-number v-model="form.order_num" :min="0" />
        </el-form-item>
        <el-form-item label="是否可见" prop="visible">
          <el-switch v-model="form.visible" />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            确认
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import {
  createPermission,
  deletePermission,
  getPermission,
  getPermissionTree,
  updatePermission,
} from '../api/permission'
import { menuTypeOptions } from '../types/permission'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import type { PermissionCreate, PermissionTree } from '../types/permission'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useResponsive } from '@/common/composables/useResponsive'
import { useCrudDialog } from '@/common/composables/useCrudDialog'

// 响应式: 平板及以上操作列固定右侧
const { isMd } = useResponsive()

// 搜索字段配置(名称/类型/状态多字段筛选, 客户端过滤树)
const searchFields: SearchField[] = [
  { prop: 'name', label: '菜单名称' },
  {
    prop: 'menu_type', label: '菜单类型', type: 'select',
    options: menuTypeOptions.map(o => ({ label: o.label, value: o.value as string })),
  },
  {
    prop: 'is_active', label: '状态', type: 'select', options: [
      { label: '启用', value: true },
      { label: '禁用', value: false },
    ],
  },
]
// 查询参数(本页为客户端过滤)
const queryParams = ref<Record<string, unknown>>({
  name: '',
  menu_type: undefined,
  is_active: undefined,
})

/** 搜索/重置(树过滤为计算属性, 无需额外处理) */
const handleSearch = () => { /* 客户端过滤自动生效 */ }

// 表格数据（树形）
const permissionTree = ref<PermissionTree[]>([])
const loading = ref(false)

// 表单验证规则
const rules = {
  name: [{ required: true, message: '请输入菜单名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入权限代码', trigger: 'blur' }],
}

// 上级菜单树数据（含根目录）
const parentTreeData = computed(() => [
  {
    id: '0',
    name: '根目录',
    children: permissionTree.value,
  },
])

// 菜单类型标签样式
const menuTypeTagType = (type: string) => {
  switch (type) {
    case 'M':
      return 'warning'
    case 'C':
      return 'primary'
    case 'F':
      return 'info'
    default:
      return 'info'
  }
}

// 菜单类型标签文字
const menuTypeLabel = (type: string) => {
  return menuTypeOptions.find((o) => o.value === type)?.label || type
}

// 节点是否匹配当前筛选条件
const nodeMatches = (node: PermissionTree) => {
  const { name, menu_type, is_active } = queryParams.value
  if (name && !node.name.includes(name as string)) return false
  if (menu_type !== undefined && node.menu_type !== menu_type) return false
  if (is_active !== undefined && node.is_active !== is_active) return false
  return true
}

// 客户端多字段过滤树（保留匹配节点的祖先链）
const filterTree = (nodes: PermissionTree[]): PermissionTree[] => {
  const hasFilter = queryParams.value.name || queryParams.value.menu_type !== undefined
    || queryParams.value.is_active !== undefined
  if (!hasFilter) return nodes
  const result: PermissionTree[] = []
  for (const node of nodes) {
    const children = filterTree(node.children || [])
    if (nodeMatches(node) || children.length > 0) {
      result.push({ ...node, children })
    }
  }
  return result
}

const filteredTree = computed(() => filterTree(permissionTree.value))

// 获取数据(权限树无分页, 与 useTableQuery 的分页列表能力不匹配, 保留手写加载)
const fetchData = async () => {
  try {
    loading.value = true
    permissionTree.value = await getPermissionTree()
  } catch (error) {
    console.error('获取权限树失败:', error)
    ElMessage.error('获取数据失败，请重试')
  } finally {
    loading.value = false
  }
}

// 编辑对话框: 新增/编辑共用(统一使用 useCrudDialog, 内置校验/重置/提交收口)
const {
  dialogVisible, formRef, submitting, form, dialogTitle,
  openCreate: handleCreate, openEdit, handleSubmit,
} = useCrudDialog({
  formBase: () => ({
    parent_id: '0',
    menu_type: 'M',
    name: '',
    code: '',
    perms: '',
    path: '',
    component: '',
    icon: '',
    order_num: 0,
    visible: true,
    is_active: true,
    description: '',
  }),
  submit: async (form, editingId) => {
    const payload: PermissionCreate = {
      parent_id: form.parent_id,
      name: form.name,
      code: form.code,
      description: form.description,
      menu_type: form.menu_type,
      path: form.path,
      component: form.component,
      perms: form.perms,
      icon: form.icon,
      order_num: form.order_num,
      visible: form.visible,
      is_active: form.is_active,
    }
    if (editingId) {
      // 更新权限
      await updatePermission(editingId, payload)
      ElMessage.success('权限更新成功')
    } else {
      // 创建权限
      await createPermission(payload)
      ElMessage.success('权限创建成功')
    }
  },
  onSaved: fetchData,
  titles: ['新增权限', '编辑权限'],
})

// 新增子项: 打开新增对话框并预填上级菜单
const handleAddChild = (row: PermissionTree) => {
  handleCreate()
  form.parent_id = row.id
}

// 打开编辑对话框(先拉取权限详情再回填表单)
const handleEdit = (row: PermissionTree) =>
  openEdit(row, async (r) => {
    const detail = await getPermission(r.id)
    return {
      parent_id: detail.parent_id || '0',
      menu_type: detail.menu_type,
      name: detail.name,
      code: detail.code,
      perms: detail.perms || '',
      path: detail.path || '',
      component: detail.component || '',
      icon: detail.icon || '',
      order_num: detail.order_num,
      visible: detail.visible,
      is_active: detail.is_active,
      description: detail.description || '',
    }
  })

// 删除操作
const handleDelete = async (row: PermissionTree) => {
  try {
    await ElMessageBox.confirm('确定要删除此权限吗？此操作不可恢复。', '警告', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })

    await deletePermission(row.id)
    ElMessage.success('删除成功')
    fetchData()
  } catch (error) {
    console.log('取消删除或删除失败:', error)
    ElMessage.error('删除失败，请重试')
  }
}

// 初始化加载数据
onMounted(() => {
  fetchData()
})
</script>
