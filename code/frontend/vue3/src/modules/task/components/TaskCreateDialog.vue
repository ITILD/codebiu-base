<template>
  <!-- 新建任务对话框(参数 JSON + 默认模板) -->
  <el-dialog v-model="dialogVisible" title="新建任务" width="90%" class="max-w-[560px]">
    <el-form ref="formRef" :model="form" :rules="createRules" label-width="80px">
      <el-form-item label="任务类型" prop="task_type">
        <el-select v-model="form.task_type" placeholder="请选择任务类型" @change="handleTypeChange">
          <el-option
            v-for="t in registry" :key="t.type"
            :label="t.name" :value="t.type"
          />
        </el-select>
        <div v-if="currentTypeDef" text-xs text-note-sub mt-1>{{ currentTypeDef.description }}</div>
      </el-form-item>
      <el-form-item label="任务名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入任务名称" maxlength="200" />
      </el-form-item>
      <el-form-item label="参数 JSON" prop="payloadText">
        <div w-full flex flex-col gap-1>
          <div flex items-center gap-2>
            <el-button size="small" text type="primary" @click="fillDefaultPayload">
              载入默认模板
            </el-button>
            <span text-xs text-note-sub>提交前会校验 JSON 格式</span>
          </div>
          <el-input
            v-model="form.payloadText"
            type="textarea" :rows="7"
            placeholder='{"key": "value"}'
            class="font-mono"
          />
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">提交任务</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { createTask } from '../api/task'
import type { TaskTypeDef } from '../types'
import { useCrudDialog } from '@/common/composables/useCrudDialog'

// 任务类型注册表(由父级编排层加载, 与搜索下拉/表格类型名共用一份数据)
const props = defineProps<{ registry: TaskTypeDef[] }>()
// 提交成功后通知父级刷新列表与统计
const emit = defineEmits<{ saved: [] }>()

// 表单校验规则(payloadText 校验 JSON 合法性)
const createRules = {
  task_type: [{ required: true, message: '请选择任务类型', trigger: 'change' }],
  name: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 1, max: 200, message: '长度在 1 到 200 个字符', trigger: 'blur' },
  ],
  payloadText: [
    {
      validator: (_rule: unknown, value: string, callback: (err?: Error) => void) => {
        if (!value.trim()) return callback()
        try {
          JSON.parse(value)
          callback()
        }
        catch {
          callback(new Error('JSON 格式不合法'))
        }
      },
      trigger: 'blur',
    },
  ],
}

// 新建任务状态收口(useCrudDialog: 打开重置/校验/提交)
const { dialogVisible, formRef, submitting, form, openCreate, handleSubmit } = useCrudDialog<{
  task_type: string
  name: string
  payloadText: string
}>({
  formBase: () => ({ task_type: '', name: '', payloadText: '' }),
  submit: async (f) => {
    // 表单规则已校验 JSON 合法性, 此处解析后投递队列
    const payload: Record<string, unknown> = f.payloadText.trim()
      ? JSON.parse(f.payloadText)
      : {}
    await createTask({ name: f.name, task_type: f.task_type, payload })
    ElMessage.success('任务已提交到队列')
  },
  onSaved: () => emit('saved'),
  failMsg: () => '创建任务失败',
})

/** 当前选中的类型定义 */
const currentTypeDef = computed(() =>
  props.registry.find(t => t.type === form.task_type),
)

/** 切换类型: 自动填充默认名称与参数模板 */
const handleTypeChange = (type: string) => {
  const def = props.registry.find(t => t.type === type)
  if (!def) return
  form.name = `${def.name}-${timeTag()}`
  form.payloadText = JSON.stringify(def.default_payload, null, 2)
}

/** 载入默认参数模板 */
const fillDefaultPayload = () => {
  if (!currentTypeDef.value) {
    ElMessage.warning('请先选择任务类型')
    return
  }
  form.payloadText = JSON.stringify(currentTypeDef.value.default_payload, null, 2)
}

/** 时间戳(默认任务命名用) */
const timeTag = () => {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
}

/** 打开新建任务对话框(重置表单防脏数据) */
const open = () => openCreate()

defineExpose({ open })
</script>
