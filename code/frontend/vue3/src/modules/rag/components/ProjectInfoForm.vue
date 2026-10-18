<template>
  <!-- 便签风表单卡片(编辑需 my_perms.update 档位>=2; 公开/私有切换需 manage_member 档位>=3 即 publish, v4 3.1) -->
  <el-form
    :model="editForm" :rules="rules" ref="editFormRef" label-width="90px"
    class="max-w-[520px] p-5 rounded-2xl bg-note-soft/60 shadow-note"
  >
    <el-form-item label="名称" prop="name">
      <el-input v-model="editForm.name" :disabled="!perms.update" placeholder="请输入知识库名称"
        maxlength="100" />
    </el-form-item>
    <el-form-item label="分类" prop="kb_category">
      <el-select v-model="editForm.kb_category" :disabled="!perms.update" placeholder="请选择分类" w-full>
        <el-option v-for="opt in kbCategoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="描述" prop="description">
      <el-input v-model="editForm.description" :disabled="!perms.update" type="textarea" :rows="3"
        placeholder="请输入描述" maxlength="500" />
    </el-form-item>
    <el-form-item label="是否私有">
      <el-tooltip :disabled="perms.manage_member" content="仅项目管理员可切换公开/私有" placement="top">
        <el-switch v-model="editForm.is_private" :disabled="!perms.manage_member" />
      </el-tooltip>
    </el-form-item>
    <el-form-item v-if="perms.update">
      <el-button class="px-6" :loading="savingBasic" @click="handleSaveBasic">保存</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
// 知识库"基本信息"编辑表单(设置抽屉 info tab): 权限位控制字段可编辑性, 保存成功 emit saved 由父级同步标题并刷新列表
import { reactive, ref, watch } from 'vue'
import { updateRagProject } from '../api/project'
import { kbCategoryOptions, type Project, type ProjectMyPerms } from '../types'
import { ElMessage, type FormInstance } from 'element-plus'

/** 基本信息表单数据 */
interface BasicForm {
  name: string
  description: string
  is_private: boolean
  kb_category: string
}

const props = defineProps<{
  /** 当前编辑的知识库项目(抽屉打开时由父级传入) */
  project: Project | null
  /** 当前用户对该项目的权限位 */
  perms: ProjectMyPerms
}>()

// 保存成功事件(携带表单值)
const emit = defineEmits<{ saved: [form: BasicForm] }>()

const rules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  kb_category: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

const editFormRef = ref<FormInstance>()
const editForm = reactive<BasicForm>({ name: '', description: '', is_private: true, kb_category: '' })
const savingBasic = ref(false)

// 项目切换时回填表单(抽屉 destroy-on-close, 打开即重建; immediate 兜底首次渲染)
watch(
  () => props.project,
  (row) => {
    if (!row) return
    Object.assign(editForm, {
      name: row.name,
      description: row.description || '',
      is_private: row.is_private,
      kb_category: row.kb_category,
    })
  },
  { immediate: true },
)

/** 保存基本信息 */
const handleSaveBasic = async () => {
  if (!editFormRef.value || !props.project) return
  const valid = await editFormRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    savingBasic.value = true
    await updateRagProject(props.project.id, { ...editForm })
    ElMessage.success('知识库更新成功')
    emit('saved', { ...editForm })
  } catch (error) {
    console.error('更新失败:', error)
    ElMessage.error('更新失败')
  } finally {
    savingBasic.value = false
  }
}
</script>
