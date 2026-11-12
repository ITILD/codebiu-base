<!-- 技能调试抽屉: 选技能 → 按 input_schema 动态渲染参数表单 → 直调 Skill 展示统一信封(REQ-018) -->
<template>
  <el-drawer v-model="drawerVisible" title="技能调试" size="92%" class="max-w-[560px]">
    <div v-if="!drawerVisible" />
    <template v-else>
      <!-- 技能选择 -->
      <el-select
        v-model="selectedKey" filterable class="w-full" placeholder="选择要调试的技能"
        @change="handleSkillChange"
      >
        <el-option v-for="s in skills" :key="s.key" :label="`${s.name} (${s.key})`" :value="s.key" />
      </el-select>

      <!-- 选中技能的形态说明 -->
      <div v-if="skill" mt-3 flex flex-col gap-1 text-xs text-note-sub>
        <span>
          执行形态: {{ skill.execution.modes.join(' / ') }}
          · inline 超时 {{ skill.execution.inline_timeout_s }}s
          · 资源域 {{ skill.execution.resource_domain }}
        </span>
        <span>能力来源: {{ natureLabel(skill.nature) }} · 副作用: {{ skill.side_effects }}</span>
      </div>

      <!-- 动态参数表单(input_schema.properties 渲染) -->
      <el-form v-if="skill" :model="formValues" label-position="top" mt-3 @submit.prevent>
        <el-form-item
          v-for="(prop, name) in formProps" :key="name"
          :label="fieldLabel(String(name), prop)" :required="requiredFields.includes(String(name))"
        >
          <!-- 枚举单选 -->
          <el-select
            v-if="selectOptions(prop).length"
            :model-value="textOf(String(name))" class="w-full" clearable
            @update:model-value="(v: string) => setText(String(name), v)"
          >
            <el-option
              v-for="opt in selectOptions(prop)" :key="String(opt)"
              :label="String(opt)" :value="String(opt)"
            />
          </el-select>
          <!-- 布尔 -->
          <el-switch
            v-else-if="prop.type === 'boolean'"
            :model-value="boolOf(String(name))"
            @update:model-value="v => setBool(String(name), v)"
          />
          <!-- 数值 -->
          <el-input-number
            v-else-if="prop.type === 'integer' || prop.type === 'number'"
            :model-value="numberOr(String(name))" class="w-full" controls-position="right"
            @update:model-value="v => setNumber(String(name), v)"
          />
          <!-- 数组/对象: JSON 文本域 -->
          <el-input
            v-else-if="prop.type === 'array' || prop.type === 'object'"
            :model-value="textOf(String(name))" type="textarea" :rows="3"
            :placeholder="`${prop.type} 类型, 请输入合法 JSON`"
            @update:model-value="(v: string) => setText(String(name), v)"
          />
          <!-- 字符串 -->
          <el-input
            v-else
            :model-value="textOf(String(name))"
            :placeholder="String(prop.description || '')"
            @update:model-value="(v: string) => setText(String(name), v)"
          />
          <div v-if="prop.description && selectOptions(prop).length" text-xs text-note-sub>
            {{ prop.description }}
          </div>
        </el-form-item>

        <el-form-item label="执行形态 (mode)">
          <el-radio-group v-model="mode">
            <el-radio-button value="auto">auto</el-radio-button>
            <el-radio-button value="inline">inline</el-radio-button>
            <el-radio-button value="queued">queued</el-radio-button>
          </el-radio-group>
          <div text-xs text-note-sub>auto 由运行时按输入规模自动选择</div>
        </el-form-item>
      </el-form>

      <div v-if="skill" flex justify-end>
        <el-button type="primary" :loading="invoking" :disabled="!skill" @click="handleInvoke">
          调用
        </el-button>
      </div>

      <!-- 无权限提示(403 属预期: skill:invoke 默认不授予普通用户) -->
      <el-alert
        v-if="forbidden" type="warning" :closable="false" mt-3
        title="无调试权限(skill:invoke)"
        description="该调试接口需要管理员授予 skill:invoke 权限, 普通用户 403 属预期; 对话入口的工具调用不受影响"
      />

      <!-- 调用失败(非 403) -->
      <el-alert
        v-if="invokeError && !forbidden" type="error" :closable="false" mt-3
        :title="invokeError"
      />

      <!-- 统一信封结果 -->
      <template v-if="envelope">
        <el-descriptions :column="1" border size="small" mt-3 title="调用结果">
          <el-descriptions-item label="调用ID">{{ envelope.invocation_id }}</el-descriptions-item>
          <el-descriptions-item label="技能键">{{ envelope.skill_key }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(envelope.status)" size="small">{{ statusLabel(envelope.status) }}</el-tag>
            <el-tag v-if="envelope.degraded" type="warning" size="small" ml-1>降级</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="形态 / 进度">
            {{ envelope.mode }} · {{ Math.round(envelope.progress) }}%
          </el-descriptions-item>
          <el-descriptions-item v-if="envelope.task_id" label="队列任务">
            {{ envelope.task_id }}
          </el-descriptions-item>
          <el-descriptions-item v-if="envelope.error" label="错误">
            <span class="text-[var(--el-color-danger)]">{{ envelope.error.class }}: {{ envelope.error.message }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="envelope.result" mt-2>
          <div text-xs text-note-sub mb-1>result</div>
          <pre
            class="m-0 p-2 text-xs rounded bg-[var(--el-fill-color-light)] overflow-auto max-h-80 whitespace-pre-wrap break-all"
          >{{ formatJson(envelope.result) }}</pre>
        </div>
      </template>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { invokeSkill } from '../api/agent'
import type { SkillInfo, SkillInvokeEnvelope, SchemaProperty } from '../types'
import { statusLabel, statusTagType, natureLabel } from '../types/labels'

const props = defineProps<{
  /** 技能清单数据源(父级已加载) */
  skills: SkillInfo[]
}>()

const drawerVisible = ref(false)
const selectedKey = ref('')
const mode = ref('auto')
const invoking = ref(false)
const envelope = ref<SkillInvokeEnvelope | null>(null)
const invokeError = ref('')
const forbidden = ref(false)
// 表单值(properties 名 → 默认值/用户输入)
const formValues = ref<Record<string, unknown>>({})

const skill = computed(() => props.skills.find(s => s.key === selectedKey.value) ?? null)
// input_schema.properties(无声明时为空对象, 不渲染参数项)
const formProps = computed<Record<string, SchemaProperty>>(() => skill.value?.input_schema?.properties ?? {})
const requiredFields = computed<string[]>(() => (skill.value?.input_schema?.required as string[]) ?? [])

/** 打开抽屉(可指定初始技能) */
const open = (skillKey?: string) => {
  drawerVisible.value = true
  envelope.value = null
  invokeError.value = ''
  forbidden.value = false
  mode.value = 'auto'
  selectedKey.value = skillKey ?? ''
  handleSkillChange()
}
defineExpose({ open })

/** 切换技能: 重置结果与表单默认值 */
const handleSkillChange = () => {
  envelope.value = null
  invokeError.value = ''
  forbidden.value = false
  const values: Record<string, unknown> = {}
  for (const [name, prop] of Object.entries(formProps.value)) {
    values[name] = defaultOf(prop)
  }
  formValues.value = values
}

/** 字段标签: 名称 + 类型 */
const fieldLabel = (name: string, prop: SchemaProperty) => `${name} (${prop.type || 'string'})`

/** 枚举选项(prop.enum) */
const selectOptions = (prop: SchemaProperty): unknown[] =>
  Array.isArray(prop.enum) ? prop.enum : []

/** 按类型取默认值 */
const defaultOf = (prop: SchemaProperty): unknown => {
  if (prop.default !== undefined) return prop.default
  switch (prop.type) {
    case 'boolean': return false
    case 'integer':
    case 'number': return undefined
    case 'array':
    case 'object': return ''
    default: return ''
  }
}

// —— 表单值类型化存取(模板内不能写联合类型断言, 收敛到 script 侧) ——
const textOf = (name: string): string => {
  const v = formValues.value[name]
  return v === undefined || v === null ? '' : String(v)
}
const setText = (name: string, v: string) => { formValues.value[name] = v }
const numberOr = (name: string): number | undefined => formValues.value[name] as number | undefined
const setNumber = (name: string, v: number | undefined) => { formValues.value[name] = v }
const boolOf = (name: string): boolean => formValues.value[name] === true
const setBool = (name: string, v: string | number | boolean) => { formValues.value[name] = v }

/** 组装并提交调用(数组/对象字段按 JSON 解析) */
const handleInvoke = async () => {
  const target = skill.value
  if (!target) return
  const input: Record<string, unknown> = {}
  for (const [name, raw] of Object.entries(formValues.value)) {
    const prop = formProps.value[name]
    if (raw === '' || raw === undefined || raw === null) continue
    if (prop?.type === 'array' || prop?.type === 'object') {
      try {
        input[name] = JSON.parse(String(raw))
      } catch {
        ElMessage.warning(`字段「${name}」不是合法 JSON`)
        return
      }
    } else {
      input[name] = raw
    }
  }
  invoking.value = true
  invokeError.value = ''
  forbidden.value = false
  try {
    envelope.value = await invokeSkill(target.key, input, mode.value)
  } catch (error) {
    // 403 属预期: skill:invoke 默认不授予, 优雅提示而非报错弹窗
    if ((error as { status?: number }).status === 403) {
      forbidden.value = true
    } else {
      invokeError.value = error instanceof Error ? error.message : '调用失败'
    }
    envelope.value = null
  } finally {
    invoking.value = false
  }
}

/** JSON 美化(解析失败原样返回) */
const formatJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>
