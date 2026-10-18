<template>
  <!-- 新建知识库对话框(编辑在抽屉中完成) -->
  <el-dialog v-model="dialogVisible" title="新建知识库" width="90%" class="max-w-[520px]">
    <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入知识库名称" maxlength="100" />
      </el-form-item>
      <el-form-item label="分类" prop="kb_category">
        <el-select v-model="form.kb_category" placeholder="请选择分类" w-full>
          <el-option v-for="opt in kbCategoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="描述" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入描述" maxlength="500" />
      </el-form-item>
      <el-form-item label="是否私有">
        <el-switch v-model="form.is_private" />
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
// 新建知识库项目对话框: 内部自持表单状态, expose.open 打开(打开时重置), 保存成功 emit saved 由父级刷新列表
import { createRagProject } from '../api/project'
import { KbCategory, kbCategoryOptions } from '../types'
import { useCrudDialog } from '@/common/composables/useCrudDialog'
import { ElMessage } from 'element-plus'

// 保存成功事件(父级刷新项目列表)
const emit = defineEmits<{ saved: [] }>()

// 表单初始值工厂(每次打开重置时调用)
const formBase = {
  name: '',
  description: '',
  is_private: true,
  kb_category: KbCategory.PROJECT as string,
}

const rules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  kb_category: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

// 新建对话框(统一使用 useCrudDialog; 编辑在抽屉中完成, 不使用 openEdit)
const {
  dialogVisible, formRef, submitting, form,
  openCreate, handleSubmit,
} = useCrudDialog({
  formBase: () => ({ ...formBase }),
  submit: async (data) => {
    await createRagProject({ ...data })
    ElMessage.success('知识库创建成功')
  },
  onSaved: () => emit('saved'),
  titles: ['新建知识库', '新建知识库'],
  failMsg: () => '创建失败',
})

/** 打开对话框(openCreate 内含表单重置) */
const open = openCreate

defineExpose({ open })
</script>
