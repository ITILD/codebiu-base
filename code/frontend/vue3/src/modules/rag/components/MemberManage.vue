<template>
  <!-- 成员管理面板(个人成员 + 部门授权): 由 project.vue 编辑抽屉内嵌使用 -->
  <el-tabs v-model="activeTab">
    <!-- Tab 1: 个人成员 -->
    <el-tab-pane label="个人成员" name="members">
      <!-- 工具行: 添加成员 -->
      <div mb-3 flex justify-end>
        <el-button type="primary" :icon="Plus" @click="handleAdd">添加成员</el-button>
      </div>

      <!-- 统一搜索栏: 多字段筛选(用户关键字/角色) -->
      <TableSearchBar
        v-model="queryParams"
        :fields="searchFields"
        :collapse-count="2"
        @search="handleSearch"
        @reset="handleSearch"
      />

      <!-- 成员表格 -->
      <el-table v-loading="loading" :data="members" border stripe>
        <el-table-column label="成员" min-width="200">
          <template #default="{ row }">
            <div flex items-center gap-2>
              <UserAvatar :size="32" :name="userLabel(row.user_id)" />
              <div>
                <div>{{ userLabel(row.user_id) }}</div>
                <div text-xs text-note-sub>{{ row.user_id }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" min-width="180" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.role" size="small" w-32 @change="(val: string) => handleRoleChange(row, val)">
              <el-option v-for="opt in ragRoleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="加入时间" min-width="130" align="center">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="100" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" plain @click="handleRemove(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 空状态提示 -->
      <div v-if="!loading && members.length === 0" py-10 flex flex-col items-center text-note-sub>
        <el-icon text-4xl mb-2><UserFilled /></el-icon>
        <p m-0>暂无成员，点击上方"添加成员"开始</p>
      </div>

      <!-- 分页(手机居中, 桌面靠右) -->
      <div mt-3 flex flex-wrap justify-center sm:justify-end>
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
          :total="total" layout="total, prev, pager, next"
          @size-change="fetchData" @current-change="fetchData" />
      </div>
    </el-tab-pane>

    <!-- Tab 2: 部门授权(部门批量授权, 子部门自动继承, 与个人档位取最高) -->
    <el-tab-pane label="部门授权" name="depts">
      <!-- 授权表单行: 部门树选择 + 档位 + 添加 -->
      <div mb-3 flex flex-wrap items-center gap-2>
        <el-tree-select v-model="deptForm.dept_id" :data="deptTreeData" :disabled="deptTreeDisabled"
          :props="{ value: 'id', label: 'name', children: 'children' }" check-strictly clearable filterable
          placeholder="选择部门(子部门自动继承)" w-64 />
        <el-select v-model="deptForm.role" w-36>
          <el-option v-for="opt in ragRoleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-button type="primary" :icon="Plus" :disabled="deptTreeDisabled" :loading="deptSubmitting"
          @click="handleAddDept">
          添加授权
        </el-button>
      </div>

      <!-- 已授权部门表格 -->
      <el-table v-loading="deptLoading" :data="deptAuths" border stripe>
        <el-table-column label="部门" min-width="200">
          <template #default="{ row }">
            <div flex items-center gap-2>
              <el-avatar :size="32" :icon="OfficeBuilding" />
              <div>
                <div>{{ deptLabel(row.dept_id) }}</div>
                <div text-xs text-note-sub>含子部门</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="授权档位" min-width="180" align="center">
          <template #default="{ row }">
            <el-select :model-value="row.role" size="small" w-32 @change="(val: string) => handleDeptRoleChange(row, val)">
              <el-option v-for="opt in ragRoleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="授权时间" min-width="130" align="center">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="100" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" plain @click="handleDeptRemove(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页(手机居中, 桌面靠右) -->
      <div mt-3 flex flex-wrap justify-center sm:justify-end>
        <el-pagination v-model:current-page="deptPagination.page" v-model:page-size="deptPagination.size"
          :total="deptTotal" layout="total, prev, pager, next"
          @size-change="fetchDeptAuths" @current-change="fetchDeptAuths" />
      </div>

      <!-- 规则说明 -->
      <el-alert type="info" :closable="false" show-icon mt-3
        title="部门授权与个人成员档位取最高档生效；授权父部门时其所有子部门用户自动继承。" />
    </el-tab-pane>
  </el-tabs>

  <!-- 添加成员对话框 -->
  <el-dialog v-model="dialogVisible" title="添加成员" width="90%" class="max-w-[480px]">
    <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
      <el-form-item label="用户" prop="user_id">
        <el-select v-model="form.user_id" filterable remote :remote-method="searchUsers"
          placeholder="输入用户名/昵称搜索" w-full :loading="userLoading">
          <el-option v-for="u in userOptions" :key="u.id" :label="`${u.nickname || u.username} (${u.username})`"
            :value="u.id">
            <div flex items-center justify-between>
              <span>{{ u.nickname || u.username }}</span>
              <span text-xs text-note-sub>{{ u.username }}</span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <el-select v-model="form.role" placeholder="请选择角色" w-full>
          <el-option v-for="opt in ragRoleOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <span>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确认</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { Plus, UserFilled, OfficeBuilding } from '@element-plus/icons-vue'
import {
  addProjectMember,
  listProjectMembers,
  removeProjectMember,
  updateProjectMember,
} from '../api/member'
import {
  addProjectDept,
  getAuthDeptTree,
  listProjectDepts,
  removeProjectDept,
  updateProjectDept,
} from '../api/deptAuth'
import { listUsers } from '@/modules/authorization/api/user'
import { ragRoleOptions, type ProjectMember, type ProjectDept } from '../types'
import TableSearchBar, { type SearchField } from '@/common/components/TableSearchBar.vue'
import UserAvatar from '@/common/components/UserAvatar.vue'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { useCrudDialog } from '@/common/composables/useCrudDialog'
import type { User } from '@/modules/authorization/types/user'
import type { DeptTree } from '@/modules/authorization/types/dept'
import { formatDate } from '@/common/utils/datetime'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps<{ /** 所属知识库项目ID */ projectId: string }>()

// 当前 Tab(members=个人成员 / depts=部门授权)
const activeTab = ref('members')

// 成员列表: 分页/查询/拉取统一收口(统一使用 useTableQuery, fetcher 闭包引用 props.projectId)
const {
  pagination, queryParams, tableData: members, total, loading,
  fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<ProjectMember>(async (params) => {
  const { user_keyword, role } = params
  // 空值不传递, 由后端进行模糊/精确过滤
  return listProjectMembers(props.projectId, {
    ...params,
    user_keyword: (user_keyword as string) || undefined,
    role: (role as string) || undefined,
  })
}, {
  defaultQuery: { user_keyword: '', role: undefined },
  errorMsg: '获取成员列表失败',
})
// 成员列表默认每页 20 条(与原实现一致)
pagination.value.size = 20

// 搜索字段配置(用户关键字/角色多字段筛选)
const searchFields: SearchField[] = [
  { prop: 'user_keyword', label: '成员', placeholder: '用户名/昵称' },
  {
    prop: 'role', label: '角色', type: 'select',
    options: ragRoleOptions.map(o => ({ label: o.label, value: o.value as string })),
  },
]
// 用户缓存(用于成员列表显示用户名)
const userMap = ref<Map<string, User>>(new Map())
const userOptions = ref<User[]>([])
// 远程搜索初始选项(打开对话框未输入时的候选, 同时为成员列表姓名映射兜底)
let initialUserOptions: User[] = []
const userLoading = ref(false)

// 添加成员对话框(统一使用 useCrudDialog)
const {
  dialogVisible, formRef, submitting, form,
  openCreate: handleAdd, handleSubmit,
} = useCrudDialog({
  formBase: () => ({ user_id: '', role: 'project_reader' }),
  submit: async (data) => {
    await addProjectMember({
      user_id: data.user_id,
      project_id: props.projectId,
      role: data.role,
    })
    ElMessage.success('成员添加成功')
  },
  onSaved: fetchData,
  titles: ['添加成员', '添加成员'],
  failMsg: () => '添加失败',
})

const rules = {
  user_id: [{ required: true, message: '请选择用户', trigger: 'change' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

// 用户显示名(优先昵称)
const userLabel = (userId: string) => {
  const u = userMap.value.get(userId)
  return u ? (u.nickname || u.username) : userId
}

// 日期格式化: 统一使用 @/common/utils/datetime (formatDate)

// 加载用户列表(初始只取一页作候选与姓名映射; 完整匹配靠远程搜索,
// 避免一次拉 500 条仅用于下拉选项, 用户量大时既慢又会静默截断)
const loadUsers = async () => {
  try {
    const res = await listUsers({ page: 1, size: 50 })
    initialUserOptions = res.items
    userOptions.value = res.items
    userMap.value = new Map(res.items.map((u) => [u.id, u]))
  } catch (error) {
    console.error('获取用户列表失败:', error)
  }
}

// 远程搜索用户(用户名/昵称两路模糊匹配合并去重, 结果同时补进姓名映射)
const searchUsers = async (query: string) => {
  const keyword = query.trim()
  if (!keyword) {
    userOptions.value = initialUserOptions
    return
  }
  userLoading.value = true
  try {
    const [byName, byNick] = await Promise.all([
      listUsers({ page: 1, size: 20, username: keyword }),
      listUsers({ page: 1, size: 20, nickname: keyword }),
    ])
    const merged: User[] = []
    const seen = new Set<string>()
    for (const u of [...byName.items, ...byNick.items]) {
      if (seen.has(u.id)) continue
      seen.add(u.id)
      merged.push(u)
      userMap.value.set(u.id, u)
    }
    userOptions.value = merged
  } catch (error) {
    console.error('搜索用户失败:', error)
  } finally {
    userLoading.value = false
  }
}

// 切换成员角色
const handleRoleChange = async (row: ProjectMember, role: string) => {
  try {
    await updateProjectMember(row.id, { role })
    row.role = role
    ElMessage.success('角色已更新')
  } catch (error) {
    console.error('角色更新失败:', error)
    ElMessage.error('角色更新失败')
  }
}

// 移除成员
const handleRemove = async (row: ProjectMember) => {
  try {
    await ElMessageBox.confirm(
      `确定移除成员"${userLabel(row.user_id)}"吗？其将失去该知识库的访问权限。`,
      '警告',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
    await removeProjectMember(row.id)
    ElMessage.success('成员已移除')
    // 移除后刷新(末行移除时自动回退翻页)
    refreshAfterRemove()
  } catch (error) {
    console.log('取消移除或移除失败:', error)
  }
}

// ---------------- 部门授权 ----------------

// 部门树数据与禁用状态(部门树加载失败时禁用选择器,不影响成员 Tab)
const deptTreeData = ref<DeptTree[]>([])
const deptTreeDisabled = ref(false)

// 部门授权列表: 统一使用 useTableQuery(首次切到部门 Tab 时由 watch 触发, 关闭自动拉取)
const {
  pagination: deptPagination, tableData: deptAuths, total: deptTotal, loading: deptLoading,
  fetchData: fetchDeptAuths, handleSearch: resetDeptPage, refreshAfterRemove: refreshDeptAfterRemove,
} = useTableQuery<ProjectDept>((params) => listProjectDepts(props.projectId, { ...params }), {
  immediate: false,
})
// 部门授权列表默认每页 20 条(与原实现一致)
deptPagination.value.size = 20

// 添加授权表单(默认只读档位)
const deptForm = reactive({ dept_id: '', role: 'project_reader' })
const deptSubmitting = ref(false)

// 部门树铺平映射(用于授权列表显示部门名, 与 userMap 模式一致)
const deptMap = computed(() => {
  const map = new Map<string, DeptTree>()
  const walk = (nodes: DeptTree[]) => {
    for (const n of nodes) {
      map.set(n.id, n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(deptTreeData.value)
  return map
})

// 部门显示名
const deptLabel = (deptId: string) => deptMap.value.get(deptId)?.name ?? deptId

// 加载部门树(走 rag 侧免 sys 权限端点)
const loadDeptTree = async () => {
  if (deptTreeData.value.length) return
  try {
    deptTreeData.value = await getAuthDeptTree()
    deptTreeDisabled.value = false
  } catch (error) {
    console.error('获取部门树失败:', error)
    deptTreeDisabled.value = true
    ElMessage.warning('部门树加载失败，部门授权暂不可用')
  }
}

// 添加部门授权
const handleAddDept = async () => {
  if (!props.projectId || !deptForm.dept_id) {
    ElMessage.warning('请先选择部门')
    return
  }
  try {
    deptSubmitting.value = true
    await addProjectDept({
      project_id: props.projectId,
      dept_id: deptForm.dept_id,
      role: deptForm.role,
    })
    ElMessage.success('部门授权添加成功')
    deptForm.dept_id = ''
    resetDeptPage()
  } catch (error) {
    console.error('部门授权添加失败:', error)
    ElMessage.error('部门授权添加失败')
  } finally {
    deptSubmitting.value = false
  }
}

// 切换部门授权档位
const handleDeptRoleChange = async (row: ProjectDept, role: string) => {
  try {
    await updateProjectDept(row.id, { role })
    row.role = role
    ElMessage.success('档位已更新')
  } catch (error) {
    console.error('档位更新失败:', error)
    ElMessage.error('档位更新失败')
  }
}

// 移除部门授权
const handleDeptRemove = async (row: ProjectDept) => {
  try {
    await ElMessageBox.confirm(
      `确定移除部门"${deptLabel(row.dept_id)}"的授权吗？该部门用户将失去对应的访问权限。`,
      '警告',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
    await removeProjectDept(row.id)
    ElMessage.success('部门授权已移除')
    // 移除后刷新(末行移除时自动回退翻页)
    refreshDeptAfterRemove()
  } catch (error) {
    console.log('取消移除或移除失败:', error)
  }
}

// 首次切到部门授权 Tab 时懒加载(减少不必要请求)
watch(activeTab, (tab) => {
  if (tab === 'depts') {
    loadDeptTree()
    fetchDeptAuths()
  }
})

// 初始化加载用户缓存(成员列表已由 useTableQuery 自动拉取)
onMounted(() => {
  loadUsers()
})

// 项目变化时刷新(回第一页重查)
watch(() => props.projectId, () => {
  handleSearch()
  if (activeTab.value === 'depts') {
    resetDeptPage()
  }
})

</script>
