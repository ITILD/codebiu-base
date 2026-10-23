// useCrudDialog 组合式函数单测(REQ-010): 新增/编辑状态机/提交成功与失败路径
import { describe, it, expect, vi } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { useCrudDialog } from './useCrudDialog'

interface Form {
  name: string
  active: boolean
}

function setup() {
  const submit = vi.fn(async () => {})
  const onSaved = vi.fn()
  const crud = useCrudDialog<Form>({
    formBase: () => ({ name: '', active: true }),
    submit,
    onSaved,
    titles: ['新增X', '编辑X'],
  })
  return { crud, submit, onSaved }
}

/** 注入表单引用桩(validate 可控) */
function stubFormRef(crud: ReturnType<typeof setup>['crud'], validate: () => Promise<void>) {
  ;(crud.formRef as unknown as { value: unknown }).value = {
    validate,
    resetFields: vi.fn(),
  }
}

describe('useCrudDialog', () => {
  it('openCreate: 重置表单并进入新增态', () => {
    const { crud } = setup()
    crud.form.name = 'dirty'
    crud.openCreate()
    expect(crud.dialogVisible.value).toBe(true)
    expect(crud.editingId.value).toBeNull()
    expect(crud.dialogTitle.value).toBe('新增X')
    expect(crud.form).toEqual({ name: '', active: true })
  })

  it('openEdit: 回填表单并进入编辑态', async () => {
    const { crud } = setup()
    await crud.openEdit({ id: 'u1' }, async () => ({ name: '张三', active: false }))
    expect(crud.editingId.value).toBe('u1')
    expect(crud.dialogTitle.value).toBe('编辑X')
    expect(crud.form).toEqual({ name: '张三', active: false })
    expect(crud.dialogVisible.value).toBe(true)
  })

  it('提交成功: submit 携带表单与编辑ID, 关闭对话框并触发 onSaved', async () => {
    const { crud, submit, onSaved } = setup()
    stubFormRef(crud, async () => {})
    await crud.openEdit({ id: 'u2' }, async () => ({ name: '李四', active: true }))
    await crud.handleSubmit()
    expect(submit).toHaveBeenCalledWith(crud.form, 'u2')
    expect(crud.dialogVisible.value).toBe(false)
    expect(onSaved).toHaveBeenCalledTimes(1)
  })

  it('表单校验失败: 不调用 submit 且对话框保持打开', async () => {
    const { crud, submit } = setup()
    stubFormRef(crud, async () => {
      throw { errors: { name: '必填' } }
    })
    crud.openCreate()
    await crud.handleSubmit()
    expect(submit).not.toHaveBeenCalled()
    expect(crud.dialogVisible.value).toBe(true)
  })

  it('submit 抛错: ElMessage 提示且对话框保持打开', async () => {
    const { crud, submit } = setup()
    stubFormRef(crud, async () => {})
    const fail = submit.mockImplementation(async () => {
      throw new Error('网络错误')
    })
    crud.openCreate()
    await crud.handleSubmit()
    expect(fail).toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalled()
    expect(crud.dialogVisible.value).toBe(true)
    expect(crud.submitting.value).toBe(false)
  })
})
