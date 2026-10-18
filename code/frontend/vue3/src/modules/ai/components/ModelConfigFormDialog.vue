<template>
  <!-- 编辑/创建对话框(按模型类型动态渲染参数) -->
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="90%" class="max-w-[640px]">
    <el-form :model="form" :rules="rules" ref="formRef" label-width="110px">
      <!-- 模型类型 -->
      <el-form-item label="模型类型" prop="model_type">
        <el-select v-model="form.model_type" w-full @change="handleTypeChange">
          <el-option v-for="opt in modelTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>

      <!-- 服务方案(按类型过滤选项) -->
      <el-form-item label="服务方案" prop="server_type">
        <el-select v-model="form.server_type" w-full>
          <el-option v-for="opt in serverTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>

      <!-- 模型标识(模型名, 由外部服务定义) -->
      <el-form-item label="模型标识" prop="model">
        <el-input v-model="form.model" placeholder="如 qwen3-asr-flash / qwen-vl-ocr-latest" />
      </el-form-item>

      <!-- 归属范围: 公共/部门/个人 -->
      <el-form-item label="归属范围" prop="scope">
        <el-radio-group v-model="form.scope" w-full>
          <el-radio v-for="opt in modelScopeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.scope === ModelScope.PUBLIC" label="默认公共" prop="is_default">
        <el-switch v-model="form.is_default" active-text="设为该类默认模型" />
      </el-form-item>
      <!-- 是否生效(仅管理员): 停用的模型前端灰色显示且不可被使用 -->
      <el-form-item v-if="isAdmin" label="是否生效" prop="is_active">
        <el-switch v-model="form.is_active" active-text="生效" inactive-text="停用" />
      </el-form-item>

      <!-- 显示名称(用于区分同名但来源不同的模型) -->
      <el-form-item label="显示名称" prop="display_name">
        <el-input v-model="form.display_name"
          placeholder="可留空, 用于区分同名但不同来源/配置的模型" maxlength="100" />
      </el-form-item>

      <!-- API 类: url / api_key(语音 online 方案同样适用) -->
      <el-form-item label="API URL" prop="url">
        <el-input v-model="form.url" placeholder="https://api.openai.com/v1" />
      </el-form-item>
      <el-form-item label="API Key" prop="api_key">
        <el-input v-model="form.api_key" placeholder="sk-..." show-password />
      </el-form-item>

      <!-- 对话模型参数 -->
      <template v-if="form.model_type === ModelType.CHAT">
        <el-form-item label="温度系数" prop="temperature">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" w-full />
        </el-form-item>
        <el-form-item label="输入tokens" prop="input_tokens">
          <el-input-number v-model="form.input_tokens" :min="1" :step="1024" w-full />
        </el-form-item>
        <el-form-item label="输出tokens" prop="out_tokens">
          <el-input-number v-model="form.out_tokens" :min="1" :step="1024" w-full />
        </el-form-item>
        <el-form-item label="禁用思考" prop="no_think">
          <el-switch v-model="form.no_think" />
        </el-form-item>
      </template>

      <!-- 嵌入模型: 维度 -->
      <el-form-item v-if="form.model_type === ModelType.EMBEDDINGS" label="向量维度" prop="out_tokens">
        <el-input-number v-model="form.out_tokens" :min="1" :step="256" w-full />
      </el-form-item>

      <!-- 重排模型: 分数范围(量纲因模型而异, 影响 score 过滤) -->
      <template v-if="form.model_type === ModelType.RERANK">
        <el-form-item label="分数范围">
          <div class="w-full flex flex-wrap items-center gap-2">
            <el-input-number v-model="rerankScoreMin" :step="0.1" controls-position="right"
              placeholder="下限" class="!w-30" />
            <span class="text-note-sub">~</span>
            <el-input-number v-model="rerankScoreMax" :step="0.1" controls-position="right"
              placeholder="上限" class="!w-30" />
            <el-button size="small" @click="applyScorePreset(0, 1)">0 ~ 1</el-button>
            <el-button size="small" @click="applyScorePreset(-0.5, 0.5)">-0.5 ~ 0.5</el-button>
          </div>
        </el-form-item>
        <el-form-item label=" ">
          <div class="text-xs text-note-sub leading-5">
            模型输出分数量纲不同：gte/Qwen3 系为 0~1，jina-reranker-v3 为 -0.5~0.5。
            配置后 score 过滤阈值统一按 0~1 归一化；不确定时保存后用"测试"按钮自动检测。
          </div>
        </el-form-item>
      </template>

      <!-- 超时与成本 -->
      <el-form-item label="超时(秒)" prop="timeout">
        <el-input-number v-model="form.timeout" :min="1" :max="600" w-full />
      </el-form-item>
      <el-form-item label="输入成本" prop="pay_in">
        <el-input-number v-model="form.pay_in" :min="0" :step="0.5" w-full />
      </el-form-item>
      <el-form-item label="输出成本" prop="pay_out">
        <el-input-number v-model="form.pay_out" :min="0" :step="0.5" w-full />
      </el-form-item>

      <!-- 扩展配置(自定义 JSON 参数, 如语音协议/音色等) -->
      <el-form-item label="扩展配置" prop="extra_text">
        <div w-full flex flex-col gap-2>
          <el-input v-model="form.extra_text" type="textarea" :rows="4"
            placeholder='JSON 对象, 如 {"protocol": "dashscope", "voice": "longxiaochun_v2"}' />
          <div v-if="extraHints.length" text-xs text-note-sub leading-5>
            <div v-for="hint in extraHints" :key="hint">· {{ hint }}</div>
          </div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        确认
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { createModelConfig, updateModelConfig, getModelConfig } from '../api/model_config'
import {
  ModelType,
  ModelScope,
  modelTypeOptions,
  serverTypeOptionsFor,
  modelScopeOptions,
  extraKeyHints,
  type ModelConfig,
  type ModelConfigCreate,
  type ModelConfigUpdate,
} from '../types/model_config'
import { ElMessage, type FormInstance } from 'element-plus'

// ################ 组件属性与事件 ################
interface Props {
  /** 是否管理员(决定"是否生效"开关展示与提交字段) */
  isAdmin: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  /** 保存成功(新增或更新), 父组件刷新列表 */
  saved: []
}>()

// ################ 表单状态(组件内部自持) ################
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const submitting = ref(false)
/** 编辑目标 ID(null 为新增态) */
const currentModelConfigId = ref<string | null>(null)

/** 表单数据(extra 以文本形式编辑) */
interface ModelConfigForm {
  model_type: ModelType
  server_type: string
  model: string
  url: string
  api_key: string
  scope: ModelScope
  is_default: boolean
  is_active: boolean
  display_name: string
  pay_in: number
  pay_out: number
  input_tokens: number
  out_tokens: number
  temperature: number
  timeout: number
  no_think: boolean
  extra_text: string
}

const defaultForm = (): ModelConfigForm => ({
  model_type: ModelType.CHAT,
  server_type: 'openai',
  model: '',
  url: '',
  api_key: '',
  scope: ModelScope.USER,
  is_default: false,
  is_active: true,
  display_name: '',
  pay_in: 0,
  pay_out: 0,
  input_tokens: 8192,
  out_tokens: 8192,
  temperature: 0.7,
  timeout: 60,
  no_think: false,
  extra_text: '',
})

const form = reactive<ModelConfigForm>(defaultForm())

const rules = {
  model: [
    { required: true, message: '请输入模型标识', trigger: 'blur' },
    { min: 1, max: 200, message: '长度在 1 到 200 个字符', trigger: 'blur' },
  ],
}

/** 对话框标题(编辑/新增) */
const dialogTitle = computed(() =>
  currentModelConfigId.value ? '编辑模型配置' : '新增模型配置')

/** 当前类型可用方案选项 */
const serverTypeOptions = computed(() => serverTypeOptionsFor(form.model_type))

/** 当前方案 extra 键提示 */
const extraHints = computed(() => extraKeyHints[form.server_type] ?? [])

// ################ extra JSON 编辑(容忍非法 JSON 的实时双向) ################
/** 容忍非法 JSON 的 extra 读取(表单实时编辑中可能尚未合法) */
const peekExtra = (): Record<string, unknown> => {
  const text = form.extra_text.trim()
  if (!text) return {}
  try {
    const obj = JSON.parse(text)
    return typeof obj === 'object' && obj !== null && !Array.isArray(obj) ? obj : {}
  }
  catch {
    return {}
  }
}

/** 写入单个 extra 键(保留其余键; 非法 JSON 时以新对象重建) */
const setExtraKey = (key: string, value: unknown) => {
  const base = peekExtra()
  if (value === undefined || value === null || Number.isNaN(value)) delete base[key]
  else base[key] = value
  form.extra_text = Object.keys(base).length ? JSON.stringify(base, null, 2) : ''
}

/** rerank 分数范围(与 extra_text 中的 score_min/score_max 双向绑定) */
const rerankScoreMin = computed<number | undefined>({
  get: () => peekExtra().score_min as number | undefined,
  set: v => setExtraKey('score_min', v),
})
const rerankScoreMax = computed<number | undefined>({
  get: () => peekExtra().score_max as number | undefined,
  set: v => setExtraKey('score_max', v),
})

/** 应用分数范围预设(0~1 通用量纲 / -0.5~0.5 jina 等量纲) */
const applyScorePreset = (min: number, max: number) => {
  setExtraKey('score_min', min)
  setExtraKey('score_max', max)
}

/** 类型切换: 重置方案为该类型第一个可用项 */
const handleTypeChange = () => {
  const options = serverTypeOptions.value
  if (!options.some(o => o.value === form.server_type)) {
    form.server_type = options[0]?.value ?? ''
  }
}

/** 解析 extra 文本为对象(空文本返回 undefined) */
const parseExtra = (): Record<string, unknown> | undefined => {
  const text = form.extra_text.trim()
  if (!text) return undefined
  try {
    const obj = JSON.parse(text)
    if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
      throw new Error('必须是 JSON 对象')
    }
    return obj as Record<string, unknown>
  }
  catch (e) {
    throw new Error(`扩展配置 JSON 无效: ${(e as Error).message}`)
  }
}

// ################ 打开/回填 ################
/** 用详情回填表单 */
const fillFromDetail = (detail: ModelConfig) => {
  form.model_type = detail.model_type
  form.server_type = detail.server_type
  form.model = detail.model || ''
  form.url = detail.url || ''
  form.api_key = detail.api_key || ''
  form.scope = detail.scope ?? ModelScope.USER
  form.is_default = detail.is_default ?? false
  form.is_active = detail.is_active ?? true
  form.display_name = detail.display_name || ''
  form.pay_in = detail.pay_in ?? 0
  form.pay_out = detail.pay_out ?? 0
  form.input_tokens = detail.input_tokens ?? 8192
  form.out_tokens = detail.out_tokens ?? 8192
  form.temperature = detail.temperature ?? 0.7
  form.timeout = detail.timeout ?? 60
  form.no_think = detail.no_think ?? false
  form.extra_text = detail.extra ? JSON.stringify(detail.extra, null, 2) : ''
}

/**
 * 打开对话框(打开前重置表单防脏数据)
 * @param row 目标行; 传入则为编辑态(拉取详情回填), 不传为新增态
 */
const open = async (row?: ModelConfig) => {
  Object.assign(form, defaultForm())
  formRef.value?.clearValidate()
  currentModelConfigId.value = row?.id ?? null
  if (row) {
    try {
      fillFromDetail(await getModelConfig(row.id))
    }
    catch (error) {
      console.error('获取模型配置详情失败:', error)
      ElMessage.error('获取模型配置详情失败')
      return
    }
  }
  dialogVisible.value = true
}

// ################ 提交 ################
/** 提交表单(创建或更新), 成功后通知父组件刷新列表 */
const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  let extra: Record<string, unknown> | undefined
  try {
    extra = parseExtra()
  }
  catch (e) {
    ElMessage.warning((e as Error).message)
    return
  }

  // 组装载荷(全部为外部服务方案, 均携带 url/api_key 等接入参数)
  const payload: ModelConfigCreate | ModelConfigUpdate = {
    model_type: form.model_type,
    server_type: form.server_type as ModelConfigCreate['server_type'],
    model: form.model,
    scope: form.scope,
    is_default: form.scope === ModelScope.PUBLIC ? form.is_default : false,
    // 仅管理员可切换生效状态(非管理员不传, 保持原值)
    is_active: props.isAdmin ? form.is_active : undefined,
    display_name: form.display_name.trim() || undefined,
    url: form.url || undefined,
    api_key: form.api_key || undefined,
    timeout: form.timeout || undefined,
    pay_in: form.pay_in ?? 0,
    pay_out: form.pay_out ?? 0,
    input_tokens: form.model_type === ModelType.CHAT ? form.input_tokens : undefined,
    out_tokens: [ModelType.CHAT, ModelType.EMBEDDINGS].includes(form.model_type)
      ? form.out_tokens
      : undefined,
    temperature: form.model_type === ModelType.CHAT ? form.temperature : undefined,
    no_think: form.model_type === ModelType.CHAT ? form.no_think : undefined,
    extra,
  }

  try {
    submitting.value = true
    if (currentModelConfigId.value) {
      await updateModelConfig(currentModelConfigId.value, payload as ModelConfigUpdate)
      ElMessage.success('更新成功')
    }
    else {
      await createModelConfig(payload as ModelConfigCreate)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    emit('saved')
  }
  catch (error) {
    console.error('保存模型配置失败:', error)
    // 透出后端校验失败的具体原因(如: 模型 url 仅支持 http/https 协议)
    ElMessage.error((error as Error)?.message || '保存失败, 请重试')
  }
  finally {
    submitting.value = false
  }
}

// 供父组件调用: 打开对话框
defineExpose({ open })
</script>
