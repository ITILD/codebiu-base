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

      <!-- 生图模型: 默认出图参数(写入 extra, 请求未传时生效) -->
      <template v-if="form.model_type === ModelType.IMAGE">
        <el-form-item label="出图尺寸">
          <el-input v-model="imageSize" placeholder="如 1024x1024(512x512 ~ 2048x2048)" class="!w-56" />
        </el-form-item>
        <el-form-item label="出图张数">
          <el-input-number v-model="imageN" :min="1" :max="4" w-full />
        </el-form-item>
        <el-form-item label="提示词改写">
          <el-switch v-model="imagePromptExtend" active-text="开启" inactive-text="关闭" />
        </el-form-item>
        <el-form-item label="图片水印">
          <el-switch v-model="imageWatermark" active-text="添加" inactive-text="不加" />
        </el-form-item>
        <el-form-item label=" ">
          <div class="text-xs text-note-sub leading-5">
            qwen-image 系列走 OpenAI 兼容协议(url 后接 /images/generations)；
            支持文生图与图生图(传参考图)；保存后可在"测试"中用提示词或参考图真实出图验证。
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

      <!-- 扩展配置: 动态键值行(键/值/注释), 常用键由"添加配置"下拉补齐 -->
      <el-form-item label="扩展配置">
        <div w-full flex flex-col gap-2>
          <!-- 列头(窄屏隐藏, 行内自行堆叠) -->
          <div v-if="extraRows.length" class="hidden sm:grid extra-grid gap-2 px-1 text-xs text-note-sub">
            <span>键名</span><span>值</span><span>注释</span><span></span>
          </div>
          <div
            v-for="(row, i) in extraRows" :key="i"
            class="extra-grid grid items-center gap-2"
          >
            <el-input v-model="row.key" size="small" placeholder="键名"
              :aria-label="`扩展配置第 ${i + 1} 项键名`" />
            <el-input v-model="row.value" size="small" placeholder="值"
              :aria-label="`扩展配置第 ${i + 1} 项值`" />
            <el-input v-model="row.comment" size="small" placeholder="注释(可选)"
              :aria-label="`扩展配置第 ${i + 1} 项注释`" />
            <el-button link type="danger" class="!p-1" :aria-label="`删除第 ${i + 1} 项`"
              @click="removeExtraRow(i)">
              <el-icon :size="14"><Delete /></el-icon>
            </el-button>
          </div>
          <div v-if="!extraRows.length" class="px-1 py-1 text-xs text-note-sub">
            暂无扩展配置，可从下方添加常用项
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <el-dropdown trigger="click" @command="addExtraRow">
              <el-button size="small" plain>+ 添加配置</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="__custom__">
                    <span text-note>自定义配置项</span>
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-for="preset in extraPresetOptions" :key="preset.key"
                    :command="preset.key" :disabled="hasExtraKey(preset.key)"
                  >
                    <span class="flex flex-col leading-tight">
                      <span class="text-note">{{ preset.key }}</span>
                      <span class="text-xs text-note-sub">{{ preset.comment }}</span>
                    </span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <span class="text-xs text-note-sub">值按 JSON 解析：数字/true/false/对象，其余按字符串</span>
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
  extraPresetsFor,
  type ExtraPresetOption,
  type ModelConfig,
  type ModelConfigCreate,
  type ModelConfigUpdate,
} from '../types/model_config'
import { Delete } from '@element-plus/icons-vue'
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

/** 表单数据(扩展配置以动态键值行编辑) */
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

// ################ 扩展配置(动态键值行) ################
/** 行注释在 extra 中的保留键(仅用于回显, 不参与模型调用) */
const EXTRA_COMMENTS_KEY = '_comments'

interface ExtraRow {
  /** 配置键 */
  key: string
  /** 值(编辑文本, 提交时按 JSON 语义解析) */
  value: string
  /** 注释(可选, 随配置保存) */
  comment: string
}

const extraRows = ref<ExtraRow[]>([])

/** 当前类型可选的常用扩展键("添加配置"下拉) */
const extraPresetOptions = computed<ExtraPresetOption[]>(() => extraPresetsFor(form.model_type))

/** 判断键是否已存在(下拉中已添加的项置灰) */
const hasExtraKey = (key: string) => extraRows.value.some(row => row.key.trim() === key)

/** 添加行: __custom__ 为空行, 其余按预设键回填默认值与注释 */
const addExtraRow = (command: string) => {
  if (command === '__custom__') {
    extraRows.value.push({ key: '', value: '', comment: '' })
    return
  }
  const preset = extraPresetOptions.value.find(item => item.key === command)
  if (!preset || hasExtraKey(preset.key)) return
  extraRows.value.push({ ...preset })
}

/** 删除行 */
const removeExtraRow = (index: number) => {
  extraRows.value.splice(index, 1)
}

/** 编辑文本 → 值: 数字/布尔/null/对象数组按 JSON 解析, 其余按字符串 */
const textToValue = (text: string): unknown => {
  const raw = text.trim()
  if (!raw) return ''
  if (raw === 'true') return true
  if (raw === 'false') return false
  if (raw === 'null') return null
  if (/^-?\d+(\.\d+)?$/.test(raw)) return Number(raw)
  if (raw.startsWith('{') || raw.startsWith('[')) {
    try {
      return JSON.parse(raw)
    }
    catch {
      return text
    }
  }
  return text
}

/** 值 → 编辑文本(字符串原样, 其余按 JSON 序列化) */
const valueToText = (value: unknown): string =>
  typeof value === 'string' ? value : JSON.stringify(value ?? '')

/** 读取当前行组成的 extra 对象 */
const peekExtra = (): Record<string, unknown> => {
  const extra: Record<string, unknown> = {}
  for (const row of extraRows.value) {
    const key = row.key.trim()
    if (key && key !== EXTRA_COMMENTS_KEY) extra[key] = textToValue(row.value)
  }
  return extra
}

/** 写入单个 extra 键(已存在则更新值, 否则追加行; 值缺失则删除该行) */
const setExtraKey = (key: string, value: unknown) => {
  const index = extraRows.value.findIndex(row => row.key.trim() === key)
  if (value === undefined || value === null || Number.isNaN(value)) {
    if (index >= 0) extraRows.value.splice(index, 1)
    return
  }
  if (index >= 0) extraRows.value[index].value = valueToText(value)
  else extraRows.value.push({ key, value: valueToText(value), comment: '' })
}

/** 行 → 提交用 extra 对象(空键忽略, 非空注释写入 _comments) */
const rowsToExtra = (): Record<string, unknown> | undefined => {
  const extra: Record<string, unknown> = {}
  const comments: Record<string, string> = {}
  for (const row of extraRows.value) {
    const key = row.key.trim()
    if (!key || key === EXTRA_COMMENTS_KEY) continue
    if (key in extra) throw new Error(`扩展配置键重复: ${key}`)
    extra[key] = textToValue(row.value)
    if (row.comment.trim()) comments[key] = row.comment.trim()
  }
  if (Object.keys(comments).length) extra[EXTRA_COMMENTS_KEY] = comments
  return Object.keys(extra).length ? extra : undefined
}

/** extra 对象 → 行(注释从 _comments 还原) */
const extraToRows = (extra?: Record<string, unknown> | null): ExtraRow[] => {
  if (!extra) return []
  const comments = (extra[EXTRA_COMMENTS_KEY] ?? {}) as Record<string, string>
  return Object.entries(extra)
    .filter(([key]) => key !== EXTRA_COMMENTS_KEY)
    .map(([key, value]) => ({ key, value: valueToText(value), comment: comments[key] ?? '' }))
}

/** rerank 分数范围(与扩展配置中的 score_min/score_max 双向绑定) */
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

/** 生图默认尺寸(与扩展配置中的 size 双向绑定) */
const imageSize = computed<string>({
  get: () => (peekExtra().size as string) ?? '',
  set: v => setExtraKey('size', v.trim() || undefined),
})
/** 生图默认张数(与扩展配置中的 n 双向绑定) */
const imageN = computed<number | undefined>({
  get: () => peekExtra().n as number | undefined,
  set: v => setExtraKey('n', v),
})
/** 提示词智能改写(与扩展配置中的 prompt_extend 双向绑定) */
const imagePromptExtend = computed<boolean>({
  get: () => (peekExtra().prompt_extend as boolean) ?? true,
  set: v => setExtraKey('prompt_extend', v),
})
/** 是否添加水印(与扩展配置中的 watermark 双向绑定) */
const imageWatermark = computed<boolean>({
  get: () => (peekExtra().watermark as boolean) ?? false,
  set: v => setExtraKey('watermark', v),
})

/** 类型切换: 重置方案为该类型第一个可用项; 生图默认放宽超时 */
const handleTypeChange = () => {
  const options = serverTypeOptions.value
  if (!options.some(o => o.value === form.server_type)) {
    form.server_type = options[0]?.value ?? ''
  }
  if (form.model_type === ModelType.IMAGE && form.timeout < 120) {
    form.timeout = 180
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
  extraRows.value = extraToRows(detail.extra)
}

/**
 * 打开对话框(打开前重置表单防脏数据)
 * @param row 目标行; 传入则为编辑态(拉取详情回填), 不传为新增态
 */
const open = async (row?: ModelConfig) => {
  Object.assign(form, defaultForm())
  extraRows.value = []
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
    extra = rowsToExtra()
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

<style scoped>
/* 扩展配置行: 窄屏堆叠, ≥640px 时为 键名/值/注释/删除 四列 */
.extra-grid {
  grid-template-columns: minmax(0, 1fr);
}

@media (min-width: 640px) {
  .extra-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.2fr) auto;
  }
}
</style>
