<template>
  <!-- 新建目录对话框 -->
  <el-dialog v-model="dialogVisible" title="新建目录" width="90%" class="max-w-[420px]">
    <el-form :model="form" :rules="nameRules" ref="formRef" label-width="80px" @submit.prevent>
      <el-form-item label="目录名" prop="name">
        <el-input v-model="form.name" placeholder="请输入目录名" maxlength="255" @keyup.enter="handleSubmit" />
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
import { ElMessage } from 'element-plus'
import { createFolder } from '../api/filesystem'
import { useCrudDialog } from '@/common/composables/useCrudDialog'

// 当前父目录ID(为空表示根目录, 由父级编排层传入)
const props = defineProps<{ pid?: string }>()
// 创建成功后通知父级刷新列表
const emit = defineEmits<{ saved: [] }>()

// 名称校验规则
const nameRules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { pattern: /^[^/\\:*?"<>|]+$/, message: '名称不能包含 / \\ : * ? " < > | 字符', trigger: 'blur' },
  ],
}

// 新建目录状态收口(useCrudDialog: 打开重置/校验/提交)
const { dialogVisible, formRef, submitting, form, openCreate, handleSubmit } = useCrudDialog<{ name: string }>({
  formBase: () => ({ name: '' }),
  submit: async (f) => {
    await createFolder(f.name.trim(), props.pid)
    ElMessage.success('目录创建成功')
  },
  onSaved: () => emit('saved'),
  failMsg: () => '创建目录失败',
})

/** 打开新建目录对话框(重置表单防脏数据) */
const open = () => openCreate()

defineExpose({ open })
</script>
