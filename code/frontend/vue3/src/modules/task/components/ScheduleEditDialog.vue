<template>
  <!-- 调度新增/编辑对话框(新增编辑共用, open 时重置) -->
  <el-dialog v-model="crud.dialogVisible.value" :title="crud.dialogTitle.value" width="90%" class="max-w-[600px]">
    <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
      <el-form-item label="任务类型" prop="task_type">
        <el-select v-model="form.task_type" placeholder="请选择任务类型" @change="handleTypeChange">
          <el-option v-for="t in registry" :key="t.type" :label="t.name" :value="t.type" />
        </el-select>
        <div v-if="currentTypeDef" text-xs text-note-sub mt-1>{{ currentTypeDef.description }}</div>
      </el-form-item>
      <el-form-item label="调度名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入调度名称" maxlength="200" />
      </el-form-item>
      <el-form-item label="触发方式" prop="kind">
        <el-radio-group v-model="form.kind">
          <el-radio value="cron">cron 表达式</el-radio>
          <el-radio value="interval">固定间隔</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.kind === 'cron'" label="cron" prop="cron">
        <div w-full flex flex-col gap-1>
          <el-input
            v-model="form.cron"
            placeholder="分 时 日 月 周, 如 0 4 * * *(每日 04:00)"
            class="font-mono"
          />
          <div flex flex-wrap gap-2>
            <el-button
              v-for="p in presets" :key="p.key"
              size="small" text type="primary"
              @click="form.cron = p.expr"
            >
              {{ presetLabel(p.key) }}
            </el-button>
          </div>
          <span text-xs text-note-sub>1=周一...7=周日(0 视为 7); 分钟级精度</span>
        </div>
      </el-form-item>
      <el-form-item v-else label="间隔(秒)" prop="intervalText">
        <div w-full flex flex-col gap-1>
          <el-input-number
            v-model="form.intervalNum"
            :min="60" :max="86400" :step="60"
            controls-position="right" w-full
          />
          <span text-xs text-note-sub>最小 60 秒(分钟级调度), 触发产生的任务沿用调度名称</span>
        </div>
      </el-form-item>
      <el-form-item label="参数 JSON" prop="payloadText">
        <div w-full flex flex-col gap-1>
          <el-button size="small" text type="primary" w-fit @click="fillDefaultPayload">
            载入默认模板
          </el-button>
          <el-input
            v-model="form.payloadText"
            type="textarea" :rows="5"
            placeholder='{"key": "value"}'
            class="font-mono"
          />
        </div>
      </el-form-item>
      <el-form-item label="立即启用">
        <el-switch v-model="form.enabled" />
        <span ml-2 text-xs text-note-sub>启用后按周期即时生效; 修改周期热生效无需重启</span>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="用途说明(可选)" maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="crud.close()">取消</el-button>
      <el-button type="primary" :loading="crud.submitting.value" @click="crud.handleSubmit()">
        {{ crud.editingId.value !== null ? '保存修改' : '创建调度' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { createSchedule, updateSchedule } from '../api/schedule'
import type { CronPreset, TaskSchedule, TaskScheduleSave, TaskTypeDef } from '../types'
import { useCrudDialog } from '@/common/composables/useCrudDialog'

// 任务类型注册表(父级编排层加载); cron 快捷预置(父级加载)
const props = defineProps<{ registry: TaskTypeDef[]; presets: CronPreset[] }>()
const emit = defineEmits<{ saved: [] }>()

/** 表单模型(kind 为触发方式视图态, 提交时折叠为 cron/interval_seconds) */
interface ScheduleForm {
  task_type: string
  name: string
  kind: 'cron' | 'interval'
  cron: string
  intervalNum: number
  payloadText: string
  enabled: boolean
  remark: string
}

// 校验规则(触发方式按 kind 分支校验对应字段)
const formRules = {
  task_type: [{ required: true, message: '请选择任务类型', trigger: 'change' }],
  name: [{ required: true, message: '请输入调度名称', trigger: 'blur' }],
  cron: [
    {
      validator: (_r: unknown, value: string, cb: (err?: Error) => void) => {
        if (form.kind !== 'cron') return cb()
        if (!value.trim()) return cb(new Error('请输入 cron 表达式'))
        cb()
      },
      trigger: 'blur',
    },
  ],
  payloadText: [
    {
      validator: (_r: unknown, value: string, cb: (err?: Error) => void) => {
        if (!value.trim()) return cb()
        try {
          JSON.parse(value)
          cb()
        }
        catch {
          cb(new Error('JSON 格式不合法'))
        }
      },
      trigger: 'blur',
    },
  ],
}

const crud = useCrudDialog<ScheduleForm>({
  formBase: () => ({
    task_type: '',
    name: '',
    kind: 'cron',
    cron: '0 4 * * *',
    intervalNum: 3600,
    payloadText: '',
    enabled: false,
    remark: '',
  }),
  titles: ['新建调度', '编辑调度'],
  submit: async (f, editingId) => {
    const data: TaskScheduleSave = {
      name: f.name,
      task_type: f.task_type,
      payload: f.payloadText.trim() ? JSON.parse(f.payloadText) : {},
      cron: f.kind === 'cron' ? f.cron.trim() : null,
      interval_seconds: f.kind === 'interval' ? f.intervalNum : null,
      enabled: f.enabled,
      remark: f.remark.trim() || null,
    }
    if (editingId !== null) await updateSchedule(Number(editingId), data)
    else await createSchedule(data)
    ElMessage.success(editingId !== null ? '调度已更新(热生效)' : '调度已创建')
  },
  onSaved: () => emit('saved'),
  failMsg: editing => (editing ? '更新调度失败' : '创建调度失败'),
})
const form = crud.form
const formRef = crud.formRef

/** 当前选中的类型定义(描述提示 + 默认模板) */
const currentTypeDef = computed(() => props.registry.find(t => t.type === form.task_type))

/** 切换类型: 自动填充默认名称与参数模板(编辑态不覆盖已有名称) */
const handleTypeChange = (type: string) => {
  const def = props.registry.find(t => t.type === type)
  if (!def) return
  if (crud.editingId.value === null) form.name = def.name
  if (!form.payloadText.trim()) form.payloadText = JSON.stringify(def.default_payload, null, 2)
}

/** 载入默认参数模板 */
const fillDefaultPayload = () => {
  if (!currentTypeDef.value) {
    ElMessage.warning('请先选择任务类型')
    return
  }
  form.payloadText = JSON.stringify(currentTypeDef.value.default_payload, null, 2)
}

/** cron 预置键中文化 */
const presetLabel = (key: string) =>
  ({ every_minute: '每分钟', hourly: '每小时', daily_4am: '每日 04:00', weekly_mon_4am: '周一 04:00', monthly_1st_4am: '每月 1 日 04:00' })[key] ?? key

/** 打开新增对话框 */
const open = () => crud.openCreate()

/** 打开编辑对话框(按行数据回填表单) */
const openEdit = (row: TaskSchedule) =>
  crud.openEdit({ id: String(row.id) }, () => ({
    task_type: row.task_type,
    name: row.name,
    kind: row.cron ? 'cron' : 'interval',
    cron: row.cron ?? '0 4 * * *',
    intervalNum: row.interval_seconds ?? 3600,
    payloadText: JSON.stringify(row.payload ?? {}, null, 2),
    enabled: row.enabled,
    remark: row.remark ?? '',
  }))

defineExpose({ open, openEdit })
</script>
