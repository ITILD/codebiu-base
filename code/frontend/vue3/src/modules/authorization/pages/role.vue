<template>
  <div p-4 md:p-6 w-full>
    <!-- 水墨页头 -->
    <InkPageHead title="角色管理" sub="角色定义与菜单授权, 权责各安其位" seal="职" />

    <!-- 统一搜索栏: 多字段筛选 -->
    <TableSearchBar
      v-model="queryParams"
      :fields="searchFields"
      @search="handleSearch"
      @reset="handleSearch"
    >
      <template #actions>
        <el-button type="primary" @click="handleCreate">新增角色</el-button>
      </template>
    </TableSearchBar>

    <!-- 数据表格 -->
    <el-table :data="tableData" v-loading="loading" stripe w-full>
      <el-table-column prop="name" label="角色名称" min-width="120" show-overflow-tooltip />
      <el-table-column prop="role_key" label="权限字符" min-width="120" show-overflow-tooltip />
      <el-table-column prop="sort" label="显示顺序" min-width="100" sortable />
      <el-table-column label="数据权限范围" min-width="160">
        <template #default="{ row }">
          {{ getDataScopeLabel(row.data_scope) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">
          <el-switch v-model="row.is_active" disabled :active-text="row.is_active ? '启用' : '禁用'" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="180" sortable />
      <!-- 操作列: 平板及以上固定右侧, 手机取消固定避免遮挡 -->
      <el-table-column label="操作" min-width="260" :fixed="isMd ? 'right' : false">
        <template #default="{ row }">
          <el-button size="small" type="primary" plain @click="handleEdit(row)">编辑</el-button>
          <el-button size="small" type="success" plain @click="handlePermission(row)">分配权限</el-button>
          <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页(手机居中, 桌面靠右) -->
    <div mt-4 flex flex-wrap justify-center sm:justify-end>
      <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
        :total="total" layout="total, prev, pager, next"
        @size-change="fetchData" @current-change="fetchData" />
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="90%" class="max-w-[600px]">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="权限字符" prop="role_key">
          <el-input v-model="form.role_key" placeholder="例如：admin、editor" />
        </el-form-item>
        <el-form-item label="显示顺序" prop="sort">
          <el-input-number v-model="form.sort" :min="0" />
        </el-form-item>
        <el-form-item label="数据权限范围" prop="data_scope">
          <el-select v-model="form.data_scope" placeholder="请选择数据权限范围">
            <el-option v-for="item in dataScopeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入角色描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">确认</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 分配权限对话框(模块声明树,勾选按钮级权限码) -->
    <el-dialog v-model="permDialogVisible" title="分配权限" width="90%" class="max-w-[700px]">
      <el-alert type="info" :closable="false" mb-3
        title="勾选权限树节点为角色授权；模块预设的通配策略(如模块管理员角色)不受影响" />
      <el-tree ref="treeRef" :data="permTreeData" show-checkbox node-key="code"
        :props="{ label: 'name', children: 'children' }" v-loading="permLoading" />
      <template #footer>
        <span>
          <el-button @click="permDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handlePermSubmit" :loading="permSubmitting">确认</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { createRole, deleteRole, getRole, listRoles, updateRole } from '../api/role'
import { getModuleTree, getRolePermCodes, syncRolePermissions } from '../api/casbin'
import type { ModulePermNode } from '../api/casbin'
import type { Role, RoleCreate } from '../types/role'
import { dataScopeOptions } from '../types/role'
import type { SearchField } from '@/common/components/TableSearchBar.vue'
import { useResponsive } from '@/common/composables/useResponsive'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { useCrudDialog } from '@/common/composables/useCrudDialog'
import { ElMessage, ElMessageBox } from 'element-plus'

// 响应式: 平板及以上操作列固定右侧
const { isMd } = useResponsive()

// 搜索字段配置(名称/权限字符/状态多字段筛选)
const searchFields: SearchField[] = [
  { prop: 'name', label: '角色名称' },
  { prop: 'role_key', label: '权限字符' },
  {
    prop: 'is_active', label: '状态', type: 'select', options: [
      { label: '启用', value: true },
      { label: '禁用', value: false },
    ]
  },
]

// 表格列表: 分页/查询/拉取统一收口(统一使用 useTableQuery, 内置末页空页回退)
const {
  pagination, queryParams, tableData, total, loading,
  fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<Role>(async (params) => {
  const { name, role_key, is_active } = params
  // 空值不传递, 由后端进行模糊/精确过滤
  const query = {
    ...params,
    name: name || undefined,
    role_key: role_key || undefined,
    is_active: is_active ?? undefined,
  }
  return listRoles(query)
}, { defaultQuery: { name: '', role_key: '', is_active: undefined } })

// 表单校验规则
const rules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  role_key: [{ required: true, message: '请输入权限字符', trigger: 'blur' }]
}

// 编辑对话框: 新增/编辑共用(统一使用 useCrudDialog, 内置校验/重置/提交收口)
const {
  dialogVisible, formRef, submitting, form, dialogTitle,
  openCreate: handleCreate, openEdit, handleSubmit,
} = useCrudDialog({
  formBase: () => ({
    name: '',
    role_key: '',
    description: '',
    sort: 0,
    data_scope: '1',
    is_active: true,
  }),
  submit: async (form, editingId) => {
    const payload: RoleCreate = {
      name: form.name,
      role_key: form.role_key,
      description: form.description,
      sort: form.sort,
      data_scope: form.data_scope,
      is_active: form.is_active
    }
    if (editingId) {
      // 更新角色
      await updateRole(editingId, payload)
      ElMessage.success('角色更新成功')
    } else {
      // 创建角色
      await createRole(payload)
      ElMessage.success('角色创建成功')
    }
  },
  onSaved: fetchData,
  titles: ['新增角色', '编辑角色'],
})

// 数据权限范围标签
const getDataScopeLabel = (value: string) => {
  return dataScopeOptions.find(o => o.value === value)?.label || value
}

// 分配权限相关
const permDialogVisible = ref(false)
const permLoading = ref(false)
const permSubmitting = ref(false)
const permTreeData = ref<ModulePermNode[]>([])
const currentRoleForPerm = ref<Role | null>(null)
const treeRef = ref()

// 打开编辑对话框(先拉取角色详情再回填表单)
const handleEdit = (row: Role) =>
  openEdit(row, async (r) => {
    const role = await getRole(r.id)
    return {
      name: role.name,
      role_key: role.role_key,
      description: role.description || '',
      sort: role.sort,
      data_scope: role.data_scope,
      is_active: role.is_active,
    }
  })

// 删除操作(删除后由 useTableQuery 的 refreshAfterRemove 统一处理末行回退翻页)
const handleDelete = async (row: Role) => {
  try {
    await ElMessageBox.confirm('确定要删除此角色吗？此操作不可恢复。', '警告', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })

    await deleteRole(row.id)
    ElMessage.success('删除成功')
    refreshAfterRemove()
  } catch (error: any) {
    // 用户取消删除，不提示错误
    if (error !== 'cancel' && error !== 'close') {
      console.error('删除失败:', error)
      ElMessage.error('删除失败，请重试')
    }
  }
}

// 打开分配权限对话框(对接模块声明树 + 角色节点权限码回显)
const handlePermission = async (row: Role) => {
  currentRoleForPerm.value = row
  permDialogVisible.value = true
  permLoading.value = true
  try {
    // 并行加载模块声明树(仅首次加载,后续复用)与角色已有权限码
    const treePromise =
      permTreeData.value.length === 0
        ? getModuleTree().then((res) => (permTreeData.value = res.data))
        : Promise.resolve()
    const codesPromise = getRolePermCodes(row.role_key)
    const [, codesRes] = await Promise.all([treePromise, codesPromise])
    // 等待树渲染后回显已选权限(仅按钮级码,父节点自动级联半选/全选)
    nextTick(() => {
      treeRef.value?.setCheckedKeys(codesRes.data || [], true)
    })
  } catch (error) {
    console.error('加载权限数据失败:', error)
    ElMessage.error('加载权限数据失败，请重试')
  } finally {
    permLoading.value = false
  }
}

// 提交权限分配(全量同步角色节点级权限,目录/菜单级码由后端忽略)
const handlePermSubmit = async () => {
  if (!currentRoleForPerm.value) return
  try {
    permSubmitting.value = true
    // 勾选节点(完全选中) + 半选父节点(勾选部分子项的目录/菜单)
    const checked: string[] = treeRef.value?.getCheckedKeys(false) || []
    const halfChecked: string[] = treeRef.value?.getHalfCheckedKeys() || []
    const codes = [...checked, ...halfChecked]

    const res = await syncRolePermissions(currentRoleForPerm.value.role_key, codes)
    ElMessage.success(res.message || '权限分配成功')
    permDialogVisible.value = false
  } catch (error) {
    console.error('权限分配失败:', error)
    ElMessage.error('权限分配失败，请重试')
  } finally {
    permSubmitting.value = false
  }
}

// 列表已由 useTableQuery 在 onMounted 自动拉取, 无需额外初始化
</script>
