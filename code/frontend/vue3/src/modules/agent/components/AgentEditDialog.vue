<!-- 智能体(助手)编辑对话框: 创建/编辑复用, 技能与知识库选项内置加载 -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑助手' : '新建助手'"
    width="90%"
    class="max-w-[560px]"
  >
    <el-form :model="form" label-width="86px" label-position="left">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="100" placeholder="如: 资料检索助手" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" maxlength="500" placeholder="一句话说明助手定位(可选)" />
      </el-form-item>
      <el-form-item label="系统提示词">
        <el-input
          v-model="form.default_prompt"
          type="textarea"
          :rows="4"
          placeholder="自定义助手的角色与行为要求; 留空使用内置默认提示词"
        />
      </el-form-item>
      <el-form-item label="技能">
        <el-select
          v-model="form.skills"
          multiple
          collapse-tags
          collapse-tags-tooltip
          class="w-full"
          placeholder="不选则为纯对话助手"
        >
          <el-option
            v-for="s in skills"
            :key="s.name"
            :label="s.display_name"
            :value="s.name"
          >
            <span flex items-center justify-between gap-3>
              <span>{{ s.display_name }}</span>
              <span v-ellipsis text-xs opacity-50 truncate max-w-50>{{ s.description }}</span>
            </span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item v-if="(form.skills ?? []).includes('rag_qa')" label="默认知识库">
        <el-select
          v-model="form.default_project_ids"
          multiple
          collapse-tags
          collapse-tags-tooltip
          class="w-full"
          placeholder="知识库问答技能未指定时的回退范围"
        >
          <el-option
            v-for="p in projects"
            :key="p.project_id"
            :label="p.project_name"
            :value="p.project_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="公开">
        <el-switch v-model="form.is_public" />
        <span ml-2 text-xs text-note-sub>公开后所有用户可在 AI 助手中使用</span>
      </el-form-item>
      <el-alert
        v-if="isEdit && agent?.is_builtin"
        title="内置助手: 仅管理员可修改, 不可删除"
        type="info"
        :closable="false"
        mb-2
      />
    </el-form>
    <template #footer>
      <span>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { createAgent, updateAgent, listSkills } from '../api/agent'
import { listMyProjects } from '@/modules/rag/api/member'
import type { AgentInfo, SkillInfo, AgentCreateReq } from '../types'
import type { MyProject } from '@/modules/rag/types'

// 保存成功后通知父级刷新列表
const emit = defineEmits<{ saved: [] }>()

const dialogVisible = ref(false)
const submitting = ref(false)
const isEdit = ref(false)
// 编辑目标(内置助手仅管理员可改, 由父级入口控制)
const agent = ref<AgentInfo | null>(null)

// 选项数据(首开懒加载)
const skills = ref<SkillInfo[]>([])
const projects = ref<MyProject[]>([])
let optionsLoaded = false

const emptyForm = (): AgentCreateReq & { is_public: boolean } => ({
  name: '',
  description: '',
  default_prompt: '',
  default_project_ids: [],
  skills: [],
  is_public: false,
})
const form = ref(emptyForm())

/** 加载技能与知识库选项(仅一次) */
const loadOptions = async () => {
  if (optionsLoaded) return
  try {
    const [skillList, projectList] = await Promise.all([
      listSkills(),
      listMyProjects({ page: 1, size: 200 }),
    ])
    skills.value = skillList
    projects.value = projectList.items
    optionsLoaded = true
  } catch (error) {
    console.error('加载技能/知识库选项失败:', error)
  }
}

/** 打开对话框(编辑传 agent, 创建不传) */
const open = async (target?: AgentInfo) => {
  agent.value = target ?? null
  isEdit.value = Boolean(target)
  form.value = target
    ? {
        name: target.name,
        description: target.description,
        default_prompt: target.default_prompt,
        default_project_ids: [...target.default_project_ids],
        skills: [...target.skills],
        is_public: target.is_public,
      }
    : emptyForm()
  dialogVisible.value = true
  await loadOptions()
}
defineExpose({ open })

/** 提交(创建/更新) */
const handleSubmit = async () => {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写助手名称')
    return
  }
  submitting.value = true
  try {
    const payload = {
      ...form.value,
      name,
      description: form.value.description?.trim() ?? '',
      default_prompt: form.value.default_prompt?.trim() ?? '',
    }
    if (isEdit.value && agent.value) {
      await updateAgent(agent.value.id, payload)
      ElMessage.success('助手已更新')
    } else {
      await createAgent(payload)
      ElMessage.success('助手已创建')
    }
    dialogVisible.value = false
    emit('saved')
  } catch (error) {
    console.error('保存助手失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>
