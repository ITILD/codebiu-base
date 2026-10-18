/**
 * CRUD 编辑对话框 composable —— 统一"新增/编辑共用对话框"的重复模式
 *
 * 收敛此前各页面重复实现的: dialogVisible / formRef / submitting /
 * editingId / form 表单对象 / dialogTitle / 重置与打开 / 提交(validate→submit→刷新)。
 *
 * 用法:
 *   const crud = useCrudDialog({
 *     formBase: () => ({ username: '', is_active: true }),
 *     submit: async (form, editingId) => { editingId ? await update(...) : await create(...) },
 *     onSaved: fetchData,
 *   })
 * 模板: <el-dialog v-model="crud.dialogVisible.value" ...>
 *   (script setup 中解构出来的 ref 需 .value; 建议整对象持有: crud.dialogVisible)
 */
import { ref, reactive, computed } from 'vue'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'

interface UseCrudDialogOptions<F extends object> {
  /** 表单初始值工厂(每次打开重置时调用) */
  formBase: () => F
  /** 提交: editingId 为 null 表示新增, 否则为编辑 */
  submit: (form: F, editingId: string | null) => Promise<void>
  /** 保存成功后的回调(通常为刷新列表) */
  onSaved?: () => void
  /** 对话框标题 [新增, 编辑] */
  titles?: [string, string]
  /** 提交失败提示文案(入参为是否编辑态) */
  failMsg?: (editing: boolean) => string
}

/**
 * 新增/编辑对话框状态与操作
 * @param options 配置项
 */
export function useCrudDialog<F extends object>(options: UseCrudDialogOptions<F>) {
  const { formBase, submit, onSaved, titles = ['新增', '编辑'], failMsg } = options

  /** 对话框显示 */
  const dialogVisible = ref(false)
  /** 表单引用(模板 <el-form ref="formRef">) */
  const formRef = ref<FormInstance>()
  /** 提交中 */
  const submitting = ref(false)
  /** 编辑目标 ID(null 为新增态) */
  const editingId = ref<string | null>(null)
  /** 表单数据(reactive, 模板直接 v-model 绑定字段) */
  const form = reactive({ ...formBase() }) as F

  /** 对话框标题 */
  const dialogTitle = computed(() => (editingId.value ? titles[1] : titles[0]))

  /** 重置表单(清空校验状态与编辑目标) */
  const resetForm = () => {
    formRef.value?.resetFields()
    editingId.value = null
    Object.assign(form, formBase())
  }

  /** 打开新增对话框 */
  const openCreate = () => {
    resetForm()
    dialogVisible.value = true
  }

  /**
   * 打开编辑对话框
   * @param row 目标行(取 row.id 为编辑 ID)
   * @param fill 由行数据构造表单值(可为异步, 如先拉详情)
   */
  const openEdit = async (row: { id: string }, fill: (row: { id: string }) => F | Promise<F>) => {
    try {
      resetForm()
      editingId.value = row.id
      Object.assign(form, await fill(row))
      dialogVisible.value = true
    } catch (error) {
      console.error('获取详情失败:', error)
      ElMessage.error('获取详情失败，请重试')
    }
  }

  /** 关闭对话框 */
  const close = () => {
    dialogVisible.value = false
  }

  /** 提交: 校验 → submit → 关闭 + onSaved; 校验/提交失败保持对话框打开 */
  const handleSubmit = async () => {
    if (!formRef.value) return
    try {
      await formRef.value.validate()
      submitting.value = true
      await submit(form, editingId.value)
      close()
      onSaved?.()
    } catch (error) {
      if (error && typeof error === 'object' && 'errors' in error) return // 表单校验失败
      console.error('操作失败:', error)
      const editing = editingId.value !== null
      ElMessage.error(failMsg?.(editing) ?? (editing ? '更新失败' : '创建失败'))
    } finally {
      submitting.value = false
    }
  }

  return { dialogVisible, formRef, submitting, editingId, form, dialogTitle, resetForm, openCreate, openEdit, close, handleSubmit }
}
