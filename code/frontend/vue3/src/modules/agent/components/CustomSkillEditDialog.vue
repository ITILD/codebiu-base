<!-- 自定义 prompt Skill 编辑对话框: 模板 + 字段声明 + 输出格式, 创建/编辑复用(REQ-018)
     编辑态打开时先调详情接口回显模板原文/字段声明/输出格式(批次 2), 全量字段正常提交 -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑自定义 Skill' : '新建自定义 Skill'"
    width="92%"
    class="max-w-[640px]"
  >
    <el-form v-loading="detailLoading" :model="form" label-width="92px" label-position="left">
      <el-form-item label="技能短名" required>
        <el-input
          v-model="form.key" :disabled="isEdit" maxlength="50"
          placeholder="小写字母开头, 仅含小写字母/数字/下划线, 如 report_summary"
        />
        <div v-if="!isEdit" text-xs text-note-sub>注册为全局键 usr.{{ form.key || '{短名}' }}, 创建后不可修改</div>
      </el-form-item>
      <el-form-item label="展示名称" required>
        <el-input v-model="form.name" maxlength="100" placeholder="如: 周报摘要" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" maxlength="500" placeholder="一句话说明技能用途(供模型判断何时调用)" />
      </el-form-item>
      <el-form-item label="提示词模板" required>
        <el-input
          v-model="form.template" type="textarea" :rows="6" maxlength="8000"
          :placeholder="templatePlaceholder"
        />
      </el-form-item>
      <el-form-item label="输出格式">
        <el-radio-group v-model="form.output_format">
          <el-radio-button value="text">text</el-radio-button>
          <el-radio-button value="json">json</el-radio-button>
        </el-radio-group>
        <span ml-2 text-xs text-note-sub>json 时将要求模型仅输出合法 JSON</span>
      </el-form-item>

      <el-form-item label="输入字段">
        <div w-full flex flex-col gap-2>
          <div v-for="(field, idx) in form.fields" :key="idx" flex items-center gap-2>
            <el-input v-model="field.name" placeholder="字段名" class="flex-1" maxlength="50" />
            <el-select v-model="field.type" class="w-28">
              <el-option label="string" value="string" />
              <el-option label="integer" value="integer" />
              <el-option label="number" value="number" />
              <el-option label="boolean" value="boolean" />
            </el-select>
            <el-checkbox v-model="field.required">必填</el-checkbox>
            <el-input v-model="field.description" placeholder="说明(可选)" class="flex-1" maxlength="200" />
            <el-button link type="danger" @click="removeField(idx)">删除</el-button>
          </div>
          <el-button plain size="small" w-fit @click="addField">+ 添加字段</el-button>
          <span text-xs text-note-sub>
            模板以 {{ fieldRefHint }} 引用输入字段; 字段未声明时运行时提供默认整段输入 input
          </span>
        </div>
      </el-form-item>

      <el-form-item label="智能体可调用">
        <el-switch v-model="form.agent_callable" />
        <span ml-2 text-xs text-note-sub>开启后智能体对话中可作为工具被模型调用</span>
      </el-form-item>
      <el-alert
        v-if="isEdit && target?.status === 'published'"
        title="已发布技能: 保存后生成新版本快照并立即重注册生效"
        type="info" :closable="false" mb-2
      />
    </el-form>
    <template #footer>
      <span>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="detailLoading" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建草稿' }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { createCustomSkill, updateCustomSkill, getCustomSkill } from '../api/agent'
import type { CustomSkillInfo, PromptFieldDef } from '../types'

// 保存成功后通知父级刷新列表
const emit = defineEmits<{ saved: [] }>()

/** 字段占位符示例(模板文本中不能直接书写花括号字面量, 收敛到 script 常量) */
const fieldRefHint = '{{字段名}}'
/** 提示词模板输入占位文案 */
const templatePlaceholder = '用 {{字段名}} 引用下方输入字段, 如: 请将以下内容整理为周报: {{content}}'

const dialogVisible = ref(false)
const submitting = ref(false)
const detailLoading = ref(false)
const isEdit = ref(false)
const target = ref<CustomSkillInfo | null>(null)

interface CustomSkillForm {
  key: string
  name: string
  description: string
  template: string
  output_format: 'text' | 'json'
  fields: PromptFieldDef[]
  agent_callable: boolean
}

const emptyForm = (): CustomSkillForm => ({
  key: '',
  name: '',
  description: '',
  template: '',
  output_format: 'text',
  fields: [],
  agent_callable: true,
})
const form = ref<CustomSkillForm>(emptyForm())

/** 追加一行字段声明 */
const addField = () => {
  form.value.fields.push({ name: '', type: 'string', required: true, description: '' })
}

/** 删除一行字段声明 */
const removeField = (idx: number) => {
  form.value.fields.splice(idx, 1)
}

/** 打开对话框(编辑传 target 先拉详情回显, 创建不传) */
const open = async (row?: CustomSkillInfo) => {
  target.value = row ?? null
  isEdit.value = Boolean(row)
  form.value = emptyForm()
  dialogVisible.value = true
  if (!row) return
  // 编辑态: 详情接口返回最新版本快照(模板原文/字段声明/输出格式), 直接回显
  try {
    detailLoading.value = true
    const detail = await getCustomSkill(row.skill_id)
    form.value = {
      key: row.key.split('.', 2)[1] ?? row.key,
      name: detail.name,
      description: detail.description,
      template: detail.template,
      output_format: detail.output_format,
      fields: detail.fields.map(f => ({ ...f })),
      agent_callable: detail.agent_callable,
    }
  } catch (error) {
    console.error('获取自定义 Skill 详情失败:', error)
    ElMessage.error('获取自定义 Skill 详情失败, 请重试')
    dialogVisible.value = false
  } finally {
    detailLoading.value = false
  }
}
defineExpose({ open })

/** 提交(创建草稿/更新, 全量字段正常提交; PUT 为部分更新语义但全量提交无害) */
const handleSubmit = async () => {
  const key = form.value.key.trim()
  const name = form.value.name.trim()
  const template = form.value.template.trim()
  if (!/^[a-z][a-z0-9_]*$/.test(key)) {
    ElMessage.warning('技能短名需小写字母开头, 仅含小写字母/数字/下划线')
    return
  }
  if (!name) {
    ElMessage.warning('请填写展示名称')
    return
  }
  if (!template) {
    ElMessage.warning('请填写提示词模板')
    return
  }
  const fields = form.value.fields
    .map(f => ({ ...f, name: f.name.trim() }))
    .filter(f => f.name)
  submitting.value = true
  try {
    if (isEdit.value && target.value) {
      await updateCustomSkill(target.value.skill_id, {
        name,
        description: form.value.description.trim(),
        template,
        output_format: form.value.output_format,
        fields,
        agent_callable: form.value.agent_callable,
      })
      ElMessage.success('自定义 Skill 已更新')
    } else {
      await createCustomSkill({
        key,
        name,
        description: form.value.description.trim(),
        template,
        output_format: form.value.output_format,
        fields,
        agent_callable: form.value.agent_callable,
      })
      ElMessage.success('草稿已创建, 发布后方可在技能清单中调用')
    }
    dialogVisible.value = false
    emit('saved')
  } catch (error) {
    console.error('保存自定义 Skill 失败:', error)
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>
