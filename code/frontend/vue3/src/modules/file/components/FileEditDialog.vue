<template>
  <!-- 编辑条目对话框(名称/描述/标签) -->
  <el-dialog v-model="dialogVisible" title="编辑条目" width="90%" class="max-w-[420px]">
    <el-form :model="form" :rules="nameRules" ref="formRef" label-width="80px" @submit.prevent>
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入名称" maxlength="255" @keyup.enter="handleSubmit" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入描述" maxlength="500" />
      </el-form-item>
      <el-form-item label="标签">
        <el-input-tag v-model="form.tags" placeholder="输入关键词后回车添加,可多个" maxlength="20" />
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
import { updateFileEntry } from '../api/filesystem'
import type { FileEntry } from '../types/file'
import { useCrudDialog } from '@/common/composables/useCrudDialog'

// 更新成功后通知父级刷新列表
const emit = defineEmits<{ saved: [] }>()

// 名称校验规则
const nameRules = {
  name: [
    { required: true, message: '请输入名称', trigger: 'blur' },
    { pattern: /^[^/\\:*?"<>|]+$/, message: '名称不能包含 / \\ : * ? " < > | 字符', trigger: 'blur' },
  ],
}

// 编辑条目状态收口(useCrudDialog: 打开重置/校验/提交)
const { dialogVisible, formRef, submitting, form, openEdit, handleSubmit } = useCrudDialog<{
  name: string
  description: string
  tags: string[]
}>({
  formBase: () => ({ name: '', description: '', tags: [] }),
  submit: async (f, editingId) => {
    if (!editingId) return
    await updateFileEntry(editingId, {
      name: f.name.trim(),
      description: f.description,
      tags: f.tags,
    })
    ElMessage.success('更新成功')
  },
  onSaved: () => emit('saved'),
})

/** 打开编辑对话框(回填行数据, 重置防脏数据) */
const open = (row: FileEntry) =>
  openEdit(row, () => ({
    name: row.name,
    description: row.description || '',
    tags: [...(row.tags || [])],
  }))

defineExpose({ open })
</script>
