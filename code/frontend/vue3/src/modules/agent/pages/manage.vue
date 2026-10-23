<!-- 智能体(助手)管理页: 助手列表 CRUD + 内置技能清单(REQ-013) -->
<template>
  <div p-4 md:p-6 w-full flex flex-col gap-4>
    <!-- 水墨页头 -->
    <InkPageHead title="助手管理" sub="智能体助手与技能注册表" seal="助" />

    <el-tabs v-model="activeTab">
      <!-- 助手列表 -->
      <el-tab-pane label="助手列表" name="agents">
        <div flex items-center gap-2 mb-3>
          <span text-xs text-note-sub>
            内置助手不可删除; 自建助手在 AI 助手页即可创建, 此处为全局视图
          </span>
          <div flex-1 />
          <el-button type="primary" @click="editDialogRef?.open()">
            <el-icon mr-1><Plus /></el-icon>新建助手
          </el-button>
        </div>
        <el-table :data="agents" v-loading="loading" stripe w-full>
          <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span flex items-center gap-1.5>
                {{ row.name }}
                <el-tag v-if="row.is_builtin" size="small" type="warning" effect="plain">内置</el-tag>
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.description || '-' }}</template>
          </el-table-column>
          <el-table-column label="技能" min-width="180">
            <template #default="{ row }">
              <template v-if="row.skills.length">
                <el-tag
                  v-for="s in row.skills" :key="s"
                  size="small" effect="plain" class="mr-1 mb-1"
                >
                  {{ skillName(s) }}
                </el-tag>
              </template>
              <span v-else text-xs text-note-sub>纯对话</span>
            </template>
          </el-table-column>
          <el-table-column label="公开" min-width="70" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_public ? 'success' : 'info'" size="small" effect="light">
                {{ row.is_public ? '公开' : '私有' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner_user_id" label="创建者" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.owner_user_id === 'system' ? '系统' : row.owner_user_id }}
            </template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="100" show-overflow-tooltip>
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="130" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editDialogRef?.open(row)">
                编辑
              </el-button>
              <el-button
                link type="danger" size="small" :disabled="row.is_builtin"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 技能清单(只读) -->
      <el-tab-pane label="技能清单" name="skills">
        <el-table :data="skills" v-loading="loading" stripe w-full>
          <el-table-column prop="display_name" label="名称" min-width="120" />
          <el-table-column prop="name" label="注册名" min-width="120" />
          <el-table-column prop="description" label="能力描述" min-width="260" show-overflow-tooltip />
          <el-table-column label="能力分级" min-width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.capability === 'read' ? 'success' : 'warning'" size="small" effect="light">
                {{ row.capability === 'read' ? '只读' : '写入' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 新建/编辑对话框 -->
    <AgentEditDialog ref="editDialogRef" @saved="loadAgents" />
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AgentEditDialog from '../components/AgentEditDialog.vue'
import { listAllAgents, listSkills, deleteAgent } from '../api/agent'
import type { AgentInfo, SkillInfo } from '../types'

const activeTab = ref('agents')
const loading = ref(false)
const agents = ref<AgentInfo[]>([])
const skills = ref<SkillInfo[]>([])
const editDialogRef = ref<InstanceType<typeof AgentEditDialog>>()

/** 技能注册名 → 展示名(预构建 Map, 避免模板中每个 tag 渲染都做 O(n) find) */
const skillNameMap = computed(() => {
  const map = new Map<string, string>()
  for (const s of skills.value) map.set(s.name, s.display_name)
  return map
})
const skillName = (name: string) => skillNameMap.value.get(name) ?? name

const loadAgents = async () => {
  loading.value = true
  try {
    agents.value = await listAllAgents()
  } catch (error) {
    console.error('获取助手列表失败:', error)
  } finally {
    loading.value = false
  }
}

const loadSkills = async () => {
  try {
    skills.value = await listSkills()
  } catch (error) {
    console.error('获取技能清单失败:', error)
  }
}

/** 删除助手(内置不可删, 按钮已禁用兜底) */
const handleDelete = async (row: AgentInfo) => {
  try {
    await ElMessageBox.confirm(
      `确定删除助手「${row.name}」吗？已绑定该助手的会话将保留但不可续聊`,
      '删除助手',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteAgent(row.id)
    ElMessage.success('已删除')
    await loadAgents()
  } catch (error) {
    if (error !== 'cancel') console.error('删除助手失败:', error)
  }
}

const formatTime = (iso: string) => {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  loadAgents()
  loadSkills()
})
</script>
