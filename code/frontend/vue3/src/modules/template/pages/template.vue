<template>
  <div p-2 md:p-4 w-full>
    <!-- 搜索栏 -->
    <div mb-5 flex flex-wrap items-center gap-2>
      <el-input v-model="searchQuery" placeholder="输入模板名称搜索" clearable @clear="handleSearch" @keyup.enter="handleSearch"
        class="w-full sm:w-80"
      >
        <template #append>
          <el-button :icon="Search" @click="handleSearch" />
        </template>
      </el-input>
      <el-button type="primary" @click="handleCreate">
        新增模板
      </el-button>
    </div>

    <!-- 数据表格 -->
    <el-table :data="tableData" v-loading="loading" border stripe w-full>
      <el-table-column v-for="column in tableColumns" :key="column.prop" :prop="column.prop" :label="column.label"
        :min-width="column.width">
        <!-- 日期 -->
        <template #default="{ row }">
          <!-- 日期 -->
          <span v-if="column.formatter">
            {{ column.formatter(row[column.prop]) }}
          </span>
          <!-- 按钮组 -->
          <template v-else-if="column.button_list">
            <template v-for="button in column.button_list">
              <el-button v-if="button.fuc_type == 'click'" size="small" :type="button.type" @click="button.fuc(row)"
                :key="button.label" plain>{{
                  button.label
                }}</el-button>
            </template>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div mt-5 flex justify-end>
      <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.size"
        :page-sizes="[10, 20, 50, 100]" :total="total" layout="total, sizes, prev, pager, next, jumper"
        @size-change="fetchData" @current-change="fetchData" />
    </div>

    <!-- 编辑/创建对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="90%" class="max-w-[600px]">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <template v-for="column in tableColumns" :key="column.prop">
          <el-form-item v-if="column.edit" :prop="column.prop" :label="column.label">
            <!-- 组件 -->
            <el-input v-if="column.edit.component == 'el-input'" v-model="form[column.prop]"
              :type="column.edit.props?.type" :rows="column.edit.props?.rows" :placeholder="column.edit.placeholder" />
            <!-- 数值输入框 -->
            <el-input-number v-if="column.edit.component == 'el-input-number'" v-model="form[column.prop]"
              :min="column.edit.props?.min" :step="column.edit.props?.step" w-full />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <span>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            确认
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { createTemplate, deleteTemplate, updateTemplate, getTemplate, listTemplates } from '../api/template'
import type { Template, TemplateCreate, TemplateUpdate } from '../types/template';
import { config, rules, formBase } from '../types/template';
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTableQuery } from '@/common/composables/useTableQuery'
import { useCrudDialog } from '@/common/composables/useCrudDialog'

// 表格行
const tableColumns: any = ref(config.tableColumns);
// 搜索条件
const searchQuery = ref('')

// 列表查询: 分页/拉取/搜索/末页空页回退统一收口(useTableQuery)
const {
  pagination, tableData, total, loading, fetchData, handleSearch, refreshAfterRemove,
} = useTableQuery<Template>(async (params) => {
  // 局部变量中转避免 TS excess property check; 空字符串不传, 由后端进行名称过滤
  const query = { ...params, name: searchQuery.value || undefined }
  return listTemplates(query)
})

// 编辑/创建对话框: 统一使用 useCrudDialog(内置校验/重置/提交收口)
// 表单字段由 tableColumns 动态渲染, 故使用宽松索引类型
const {
  dialogVisible, formRef, submitting, form, dialogTitle,
  openCreate: handleCreate, openEdit, handleSubmit,
} = useCrudDialog<Record<string, any>>({
  // 深拷贝 formBase, 避免共享引用
  formBase: () => JSON.parse(JSON.stringify(formBase)),
  submit: async (form, editingId) => {
    if (editingId) {
      // 更新模板
      const updateData: TemplateUpdate = {
        name: form.name,
        description: form.description,
        value: form.value
      }
      await updateTemplate(editingId, updateData)
      ElMessage.success('模板更新成功')
    } else {
      // 创建模板
      const createData: TemplateCreate = {
        name: form.name,
        description: form.description,
        value: form.value
      }
      await createTemplate(createData)
      ElMessage.success('模板创建成功')
    }
  },
  onSaved: fetchData,
  titles: ['新增模板', '编辑模板'],
})

// 打开编辑对话框(先拉取模板详情再回填表单)
const handleEdit = (row: Template) =>
  openEdit(row, async () => {
    const template = await getTemplate(row.id)
    return {
      name: template.name,
      description: template.description || '',
      value: template.value ?? 0,
    }
  })

// 删除操作
const handleDelete = async (row: Template) => {
  try {
    await ElMessageBox.confirm('确定要删除此模板吗？此操作不可恢复。', '警告', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })

    // 调用删除API
    await deleteTemplate(row.id)
    ElMessage.success('删除成功')

    // 删除后末行回退翻页统一由 useTableQuery 处理
    refreshAfterRemove()
  } catch (error) {
    console.log('取消删除或删除失败:', error)
    ElMessage.error('删除失败，请重试')
  }
}

// 最后一个元素默认为操作按钮组
const button_list = tableColumns.value.at(-1)?.button_list
if (button_list) {
  button_list['edit'].fuc = handleEdit
  button_list['delete'].fuc = handleDelete
}
</script>