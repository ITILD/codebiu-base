<template>
  <div p-3 md:p-4 w-full>
    <!-- 后台页头 -->
    <InkPageHead title="用户管理" sub="账户信息与角色授权" seal="员" />

    <!-- 统一搜索栏: 多字段筛选 + 主操作 -->
    <TableSearchBar
      v-model="queryParams"
      :fields="searchFields"
      @search="handleSearch"
      @reset="handleSearch"
    >
      <template #actions>
        <el-button size="small" type="primary" @click="handleCreate">新增用户</el-button>
      </template>
    </TableSearchBar>

    <!-- 数据表格: ProTable 统一列设置/密度/多选/移动端卡片 -->
    <ProTable
      ref="proTableRef"
      :columns="columns"
      :data="tableData"
      :loading="loading"
      table-key="auth-user"
      card-title-prop="username"
      selectable
      @selection-change="(rows) => (selectedRows = rows as unknown as User[])"
    >
      <template #toolbar>
        <span text-xs text-note-sub>共 {{ total }} 个用户</span>
      </template>

      <template #col-dept_id="{ row }">
        {{ getDeptName(row.dept_id) || '—' }}
      </template>

      <template #col-is_active="{ row }">
        <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
          {{ row.is_active ? '启用' : '禁用' }}
        </el-tag>
      </template>

      <template #row-actions="{ row }">
        <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
        <el-button link type="primary" size="small" @click="handleAssignRole(row)">角色</el-button>
        <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
      </template>

      <!-- 批量操作条: 启用/禁用/删除 -->
      <template #batch-actions="{ rows }">
        <el-button size="small" :disabled="batchBusy" @click="handleBatchToggle(rows as unknown as User[], true)">
          批量启用
        </el-button>
        <el-button size="small" :disabled="batchBusy" @click="handleBatchToggle(rows as unknown as User[], false)">
          批量禁用
        </el-button>
        <el-button
          size="small"
          type="danger"
          plain
          :loading="deleting"
          @click="handleBatchDelete(rows as unknown as User[])"
        >
          批量删除
        </el-button>
      </template>
    </ProTable>

    <!-- 分页(手机居中, 桌面靠右) -->
    <div mt-3 flex flex-wrap justify-center sm:justify-end>
      <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
        :total="total" layout="total, prev, pager, next" small
        @size-change="fetchData" @current-change="fetchData" />
    </div>

    <!-- 编辑/创建对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="90%" class="max-w-[500px]">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item prop="username" label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="部门">
          <el-tree-select v-model="form.dept_id" :data="deptTreeData" :props="{ value: 'id', label: 'name', children: 'children' }"
            check-strictly placeholder="请选择部门" clearable w-full />
        </el-form-item>
        <el-form-item prop="email" label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱地址" />
        </el-form-item>
        <el-form-item prop="phone" label="电话">
          <el-input v-model="form.phone" placeholder="请输入电话号码" />
        </el-form-item>
        <el-form-item prop="nickname" label="昵称">
          <el-input v-model="form.nickname" placeholder="请输入昵称" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">确认</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 分配角色对话框 -->
    <el-dialog v-model="roleDialogVisible" title="分配角色" width="90%" class="max-w-[500px]">
      <div mb-3>
        <span>用户名: <strong>{{ currentUserForRole?.username }}</strong></span>
      </div>
      <el-checkbox-group v-model="selectedRoleKeys">
        <div v-for="role in allRoles" :key="role.id" mb-2>
          <el-checkbox :value="role.role_key" :label="`${role.name} (${role.role_key})`" />
        </div>
      </el-checkbox-group>
      <template #footer>
        <span>
          <el-button @click="roleDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmitRoles" :loading="roleSubmitting">确认</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import {
  batchDeleteUsers,
  batchUpdateUsersStatus,
  createUser,
  deleteUser,
  updateUser,
  getUser,
  listUsers,
} from '../api/user'
import { getDeptTree } from '../api/dept'
import { listAllRoles } from '../api/role'
import { getRolesForUser, batchAddUserRoles } from '../api/casbin'
import type { User, UserCreate, UserUpdate } from '../types/user'
import type { DeptTree } from '../types/dept'
import type { Role } from '../types/role'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import ProTable from '@/common/components/pro-table/ProTable.vue'
import type { ProTableColumn } from '@/common/components/pro-table/useProTablePrefs'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { useCrudDialog } from '@/common/composables/useCrudDialog'
import { useBatchDelete } from '@/common/composables/useBatchDelete'
import { formatDateTime } from '@/common/utils/datetime'
import { ElMessage, ElMessageBox, type FormRules } from 'element-plus'

// 搜索字段配置(用户名/昵称/状态多字段筛选)
const searchFields: SearchField[] = [
  { prop: 'username', label: '用户名' },
  { prop: 'nickname', label: '昵称' },
  {
    prop: 'is_active', label: '状态', type: 'select', options: [
      { label: '启用', value: true },
      { label: '禁用', value: false },
    ]
  },
]

// 列配置: 部门/状态走插槽, 时间走 formatter
const columns: ProTableColumn[] = [
  { prop: 'username', label: '用户名', minWidth: 130 },
  { prop: 'nickname', label: '昵称', minWidth: 110 },
  { prop: 'dept_id', label: '部门', minWidth: 130, slot: true },
  { prop: 'email', label: '邮箱', minWidth: 170 },
  { prop: 'phone', label: '电话', minWidth: 120 },
  { prop: 'is_active', label: '状态', minWidth: 90, align: 'center', slot: true },
  {
    prop: 'created_at', label: '创建时间', minWidth: 160,
    formatter: (row) => formatDateTime(row.created_at as string),
  },
]

// 表格列表: 分页/查询/拉取统一收口(useTableQuery, 内置末页空页回退)
const {
  pagination, queryParams, tableData, total, loading,
  fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<User>(async (params) => {
  // 空值不传递, 由后端进行模糊/精确过滤(queryParams 为宽类型, 此处收敛为标量)
  const query = {
    ...params,
    username: (params.username as string) || undefined,
    nickname: (params.nickname as string) || undefined,
    is_active: (params.is_active as boolean | undefined) ?? undefined,
  }
  return listUsers(query)
}, { defaultQuery: { username: '', nickname: '', is_active: undefined } })

// 多选状态(ProTable 批量操作条 / 清空选择)
const proTableRef = ref<InstanceType<typeof ProTable>>()
const selectedRows = ref<User[]>([])
const { batchDelete, deleting } = useBatchDelete()
const batchUpdating = ref(false)
// 任一批量任务进行中时禁用其他批量入口
const batchBusy = computed(() => deleting.value || batchUpdating.value)

// 部门树数据
const deptTreeData = ref<DeptTree[]>([])

// 验证规则
const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '长度在 3 到 50 个字符', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }
  ],
  phone: [
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号码', trigger: 'blur' }
  ],
}

// 编辑对话框: 新增/编辑共用(useCrudDialog, 内置校验/重置/提交收口)
const {
  dialogVisible, formRef, submitting, editingId, form, dialogTitle,
  openCreate: handleCreate, openEdit, handleSubmit,
} = useCrudDialog({
  formBase: () => ({
    username: '',
    dept_id: null as string | null,
    email: '',
    phone: '',
    nickname: '',
    is_active: true,
  }),
  submit: async (form, editingId) => {
    if (editingId) {
      const updateData: UserUpdate = {
        username: form.username,
        dept_id: form.dept_id || undefined,
        email: form.email,
        phone: form.phone,
        nickname: form.nickname,
        is_active: form.is_active
      }
      await updateUser(editingId, updateData)
      ElMessage.success('用户更新成功')
    } else {
      const createData: UserCreate = {
        username: form.username,
        password: '123456',
        dept_id: form.dept_id || undefined,
        email: form.email,
        phone: form.phone,
        nickname: form.nickname,
        is_active: form.is_active
      }
      await createUser(createData)
      ElMessage.success('用户创建成功')
    }
  },
  onSaved: fetchData,
  titles: ['新增用户', '编辑用户'],
})

// 角色分配相关
const roleDialogVisible = ref(false)
const roleSubmitting = ref(false)
const currentUserForRole = ref<User | null>(null)
const allRoles = ref<Role[]>([])
const selectedRoleKeys = ref<string[]>([])

// 获取部门名称
const getDeptName = (deptId?: string) => {
  if (!deptId) return ''
  const findDept = (nodes: DeptTree[]): string => {
    for (const node of nodes) {
      if (node.id === deptId) return node.name
      if (node.children?.length) {
        const found = findDept(node.children)
        if (found) return found
      }
    }
    return ''
  }
  return findDept(deptTreeData.value)
}

// 加载部门树
const fetchDeptTree = async () => {
  try {
    deptTreeData.value = await getDeptTree()
  } catch (error) {
    console.error('获取部门树失败:', error)
  }
}

// 加载所有角色
const fetchAllRoles = async () => {
  try {
    allRoles.value = await listAllRoles()
  } catch (error) {
    console.error('获取角色列表失败:', error)
  }
}

// 打开编辑对话框(先拉取用户详情再回填表单)
const handleEdit = (row: User) =>
  openEdit(row, async (r) => {
    const user = await getUser(r.id)
    return {
      username: user.username,
      dept_id: user.dept_id || null,
      email: user.email || '',
      phone: user.phone || '',
      nickname: user.nickname || '',
      is_active: user.is_active ?? true,
    }
  })

// 单条删除
const handleDelete = async (row: User) => {
  try {
    await ElMessageBox.confirm('确定要删除此用户吗？此操作不可恢复。', '警告', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await deleteUser(row.id)
    ElMessage.success('删除成功')
    refreshAfterRemove()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('删除失败，请重试')
    }
  }
}

/** 批量删除: 走后端批量接口(一次请求), 汇总后刷新并清空选择 */
const handleBatchDelete = async (rows: User[]) => {
  const removed = await batchDelete({
    rows,
    getId: (row) => row.id,
    removeMany: (ids) => batchDeleteUsers(ids.map(String)),
    label: (row) => row.username,
    onRemoved: async (n) => {
      await refreshAfterRemove(n)
      proTableRef.value?.clearSelection()
    },
  })
  if (removed) selectedRows.value = []
}

/** 批量启用/禁用(仅提交状态变化项, 避免无效请求) */
const handleBatchToggle = async (rows: User[], active: boolean) => {
  const targets = rows.filter((row) => Boolean(row.is_active) !== active)
  if (!targets.length) {
    ElMessage.info(`所选用户已是${active ? '启用' : '禁用'}状态`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${targets.length} 个用户设为${active ? '启用' : '禁用'}吗？`,
      '状态变更',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  batchUpdating.value = true
  try {
    const res = await batchUpdateUsersStatus(targets.map((row) => row.id), active)
    ElMessage.success(`已更新 ${res.updated_count} 个用户`)
    await fetchData()
    proTableRef.value?.clearSelection()
    selectedRows.value = []
  } catch {
    ElMessage.error('批量更新失败，请重试')
  } finally {
    batchUpdating.value = false
  }
}

// 分配角色
const handleAssignRole = async (row: User) => {
  currentUserForRole.value = row
  selectedRoleKeys.value = []
  roleDialogVisible.value = true
  // 确保角色列表已加载
  if (allRoles.value.length === 0) {
    await fetchAllRoles()
  }
  // 加载用户当前角色
  try {
    const res = await getRolesForUser(row.id)
    selectedRoleKeys.value = res.data || []
  } catch (error) {
    console.error('获取用户角色失败:', error)
  }
}

// 提交角色分配
const handleSubmitRoles = async () => {
  if (!currentUserForRole.value) return
  try {
    roleSubmitting.value = true
    await batchAddUserRoles({
      user_id: currentUserForRole.value.id,
      role_keys: selectedRoleKeys.value,
      dom: '*'
    })
    ElMessage.success('角色分配成功')
    roleDialogVisible.value = false
  } catch (error) {
    console.error('角色分配失败:', error)
    ElMessage.error('角色分配失败，请重试')
  } finally {
    roleSubmitting.value = false
  }
}

// 初始化加载辅助数据(列表已由 useTableQuery 自动拉取)
onMounted(() => {
  fetchDeptTree()
  fetchAllRoles()
})
</script>
