// src/modules/ai/types/model_config.ts
// 模型配置类型定义(多类型模型: chat/embeddings/rerank/ocr/asr/tts/image)

/** 模型服务方案(与后端 ModelServerType 对齐; 模型能力全部通过外部服务接入) */
enum ModelServerType {
  OPENAI = "openai",
  DASHSCOPE = "dashscope",
  VLLM = "vllm",
  OLLAMA = "ollama",
  AWS = "aws",
  /** 历史方案值(本地推理已下线, 仅为兼容存量数据展示保留, 不可新建) */
  SHERPA = "sherpa",
  QWEN = "qwen",
  PADDLE = "paddle",
  ONLINE = "online",
  LOCAL = "local",
}

/** 模型类型(与后端 ModelType 对齐; vad/denoise 为历史类型值已下线) */
enum ModelType {
  CHAT = "chat",
  EMBEDDINGS = "embeddings",
  RERANK = "rerank",
  OCR = "ocr",
  ASR = "asr",
  TTS = "tts",
  /** 生图: 文生图(T2I)/图生图·图像编辑(I2I) */
  IMAGE = "image",
  VAD = "vad",
  DENOISE = "denoise",
}

/** 模型归属/可见范围(与后端 ModelScope 对齐) */
enum ModelScope {
  /** 公共: 所有用户和部门可见可用 */
  PUBLIC = "public",
  /** 部门: 仅创建者所在部门可见可用 */
  DEPT = "dept",
  /** 个人: 仅创建者本人可见可用 */
  USER = "user",
}

/** 归属范围显示选项 */
const modelScopeOptions: { label: string; value: ModelScope }[] = [
  { label: '公共(所有人可见)', value: ModelScope.PUBLIC },
  { label: '部门(本部门可见)', value: ModelScope.DEPT },
  { label: '个人(仅自己可见)', value: ModelScope.USER },
]

/** 归属范围短标签(列表/下拉用) */
const scopeShortLabel = (scope?: ModelScope) =>
  ({ [ModelScope.PUBLIC]: '公共', [ModelScope.DEPT]: '部门', [ModelScope.USER]: '个人' })[scope ?? ModelScope.USER] ?? '个人'

/**
 * 模型显示主名(优先 display_name, 用于区分同名不同来源/配置的模型)
 */
const modelMainLabel = (config: { display_name?: string; model: string }) =>
  config.display_name?.trim() || config.model

/**
 * 模型区分键: 用于区分同名但来源/配置不同的模型(供唯一 key 使用)
 */
const modelKeyLabel = (config: { model: string; server_type: string; scope?: ModelScope }) =>
  `${config.model}|${config.server_type}|${config.scope ?? ModelScope.USER}`

/** 模型类型显示选项(vad/denoise 本地方案已下线, 不再提供创建) */
const modelTypeOptions: { label: string; value: ModelType }[] = [
  { label: '对话', value: ModelType.CHAT },
  { label: '嵌入', value: ModelType.EMBEDDINGS },
  { label: '重排', value: ModelType.RERANK },
  { label: 'OCR', value: ModelType.OCR },
  { label: '语音识别', value: ModelType.ASR },
  { label: '语音合成', value: ModelType.TTS },
  { label: '生图', value: ModelType.IMAGE },
]

/** 历史类型值中文标签(仅存量数据渲染用) */
const legacyTypeLabels: Record<string, string> = {
  [ModelType.VAD]: 'VAD断句(已下线)',
  [ModelType.DENOISE]: '降噪(已下线)',
}

/** 模型类型标签样式(element-plus tag type) */
const modelTypeTagType: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
  [ModelType.CHAT]: 'primary',
  [ModelType.EMBEDDINGS]: 'success',
  [ModelType.RERANK]: 'warning',
  [ModelType.OCR]: 'danger',
  [ModelType.ASR]: 'info',
  [ModelType.TTS]: 'info',
  [ModelType.IMAGE]: 'success',
  [ModelType.VAD]: 'info',
  [ModelType.DENOISE]: 'info',
}

/** API 类方案(远程推理: 需要 url/api_key) */
const API_SERVER_OPTIONS = [
  { label: 'OpenAI', value: ModelServerType.OPENAI },
  { label: 'DashScope', value: ModelServerType.DASHSCOPE },
  { label: 'VLLM', value: ModelServerType.VLLM },
  { label: 'Ollama', value: ModelServerType.OLLAMA },
  { label: 'AWS', value: ModelServerType.AWS },
]

/** 语音方案: 在线(远程API或本地vllm发布的OpenAI兼容接口) */
const VOICE_ONLINE_OPTIONS = [
  { label: '在线(远程API/本地vllm发布)', value: ModelServerType.ONLINE },
]

/**
 * 按模型类型返回可用的服务方案(与后端 server_types_for 对齐; 全部为外部服务接入)
 * - asr/tts: online(远程API/本地vllm发布)
 * - ocr: dashscope(阿里云在线)
 * - image: openai(OpenAI 兼容生图)/dashscope(百炼兼容模式, 协议相同)
 * - 其余(chat/embeddings/rerank): openai/dashscope/vllm/ollama/aws
 */
const serverTypeOptionsFor = (modelType: string) => {
  if ([ModelType.ASR, ModelType.TTS].includes(modelType as ModelType)) {
    return VOICE_ONLINE_OPTIONS
  }
  if ([ModelType.VAD, ModelType.DENOISE].includes(modelType as ModelType)) {
    return []
  }
  if (modelType === ModelType.OCR) {
    return [{ label: 'DashScope(阿里云在线)', value: ModelServerType.DASHSCOPE }]
  }
  if (modelType === ModelType.IMAGE) {
    return [
      { label: 'OpenAI 兼容(生图)', value: ModelServerType.OPENAI },
      { label: 'DashScope(百炼兼容模式)', value: ModelServerType.DASHSCOPE },
    ]
  }
  return API_SERVER_OPTIONS
}

/** 模型类型中文标签 */
const modelTypeLabel = (type: string) =>
  modelTypeOptions.find(o => o.value === type)?.label ?? legacyTypeLabels[type] ?? type

/** 方案中文标签 */
const serverTypeLabel = (type: string) =>
  [...API_SERVER_OPTIONS, ...VOICE_ONLINE_OPTIONS].find(o => o.value === type)?.label ?? type

interface ModelConfigBase {
  model_type: ModelType;
  server_type: ModelServerType;
  model: string;
  url?: string;
  api_key?: string;
  /** 归属范围(public=所有人可见, dept=本部门可见, user=仅本人可见) */
  scope?: ModelScope;
  /** 归属部门ID(scope=dept 时服务端自动填充) */
  dept_id?: string;
  /** 是否为该模型类型的默认公共模型(scope=public 且同类型唯一) */
  is_default?: boolean;
  /** 是否生效: 不生效的模型(启动 seed 未启用/管理员停用)灰色显示且不可被使用 */
  is_active?: boolean;
  /** 显示名称: 用于区分同名但来源/配置不同的模型(留空取 model) */
  display_name?: string;
  pay_in?: number;
  pay_out?: number;
  input_tokens?: number;
  out_tokens?: number;
  temperature?: number;
  timeout?: number;
  no_think?: boolean;
  /** 扩展配置(语音类: 模型路径/设备/线程等) */
  extra?: Record<string, any>;
}

interface ModelConfig extends ModelConfigBase {
  id: string;
  user_id: string;
  created_at: string; // ISO格式日期字符串
  updated_at: string; // ISO格式日期字符串
  /** 最近一次校验是否可用(后台自动校验回写, null=未校验) */
  check_valid?: boolean | null;
  /** 最近一次校验是否支持格式化输出(仅chat类, null=未校验/不适用) */
  check_format?: boolean | null;
  /** 最近一次校验时间 */
  checked_at?: string | null;
  /** 各能力测试明细(capability -> 结果), null=未测试 */
  check_result?: Record<string, ModelCapabilityResult> | null;
}

/** rerank 分数范围检测建议(与后端 _test_rerank 的 suggest 对齐) */
interface RerankScoreSuggest {
  observed_min: number;
  observed_max: number;
  configured_min: number;
  configured_max: number;
  need_fix?: boolean;
  /** 建议写入 extra 的分数范围(need_fix 时提供) */
  score_min?: number;
  score_max?: number;
}

/** 单项能力测试结果(与后端 ModelCapabilityTestItem 对齐) */
interface ModelCapabilityResult {
  capability: string;
  label: string;
  ok: boolean;
  detail?: string;
  error?: string;
  elapsed?: number;
  checked_at?: string;
  /** 附加建议(rerank: 分数范围检测) */
  suggest?: RerankScoreSuggest | null;
}

/** 模型能力测试响应(POST /ai/llm/test-by-model-id) */
interface ModelTestResponse {
  model_id: string;
  model_type: string;
  capabilities: ModelCapabilityResult[];
  checked_at?: string;
}

/** 模型单独测试明细项(rerank 排序打分 / ocr 识别行) */
interface ModelCustomTestItem {
  /** rerank: 原始文档序号 / ocr: 行序号 */
  index?: number;
  /** rerank: 原始文档内容 */
  document?: string;
  /** rerank: 原始分 */
  score?: number;
  /** rerank: 归一化分 */
  normalized?: number;
  /** ocr: 行文本 */
  text?: string;
}

/** 模型单独测试响应(POST /ai/llm/test-custom, 自定义参数单次真实调用) */
interface ModelCustomTestResponse {
  model_id: string;
  model_type: string;
  capability: string;
  ok: boolean;
  /** 结果摘要(向量维度/排序结论等) */
  detail?: string;
  /** 完整回答(chat) */
  answer?: string;
  /** 明细列表(rerank 打分排序) */
  results?: ModelCustomTestItem[];
  elapsed?: number;
  error?: string;
}

/** ASR/OCR 单独测试响应(POST /ai/llm/test-asr | /test-ocr) */
interface ModelMediaTestResponse {
  ok: boolean;
  /** 识别全文 */
  text?: string;
  /** ocr: 明细行 */
  results?: ModelCustomTestItem[];
  elapsed?: number;
}

/** 单张生图结果(与后端 ImageResultItem 对齐) */
interface ModelImageResultItem {
  /** 图片地址(临时地址, 约 24 小时有效) */
  url: string;
  /** 模型改写后的提示词(部分模型返回) */
  revised_prompt?: string;
}

/** 生图单独测试响应(POST /ai/llm/test-image, 与后端 ImageGenerateResponse 对齐) */
interface ModelImageTestResponse {
  model_id?: string | null;
  model?: string;
  /** image=文生图 / image_edit=图生图 */
  capability?: string;
  ok: boolean;
  images: ModelImageResultItem[];
  elapsed?: number;
  error?: string;
}

/** 各模型类型支持的能力项(capability -> 中文名, 与后端 MODEL_CAPABILITIES 对齐) */
const capabilityOptionsFor: Record<string, { key: string; label: string }[]> = {
  [ModelType.CHAT]: [
    { key: 'chat', label: '问答' },
    { key: 'structured', label: '结构化' },
    { key: 'vision', label: '多模态' },
  ],
  [ModelType.EMBEDDINGS]: [{ key: 'embedding', label: '向量化' }],
  [ModelType.RERANK]: [{ key: 'rerank', label: '重排' }],
  // 语音类: 后端用模拟音频对在线引擎做冒烟验证
  [ModelType.ASR]: [{ key: 'asr', label: '识别' }],
  [ModelType.TTS]: [{ key: 'tts', label: '合成' }],
  // 生图类: 文生图与图生图(图像编辑)各生成一张小图验证
  [ModelType.IMAGE]: [
    { key: 'image', label: '文生图' },
    { key: 'image_edit', label: '图生图' },
  ],
}

/** 取模型已测试的能力列表(含未通过, 供标签渲染; 未测试返回 [])
 *  通过/失败仅靠颜色区分: ok=绿, 失败=红 */
const testedCapabilities = (config?: ModelConfig | null) =>
  Object.entries(config?.check_result ?? {})
    .filter(([, v]) => !!v)
    .map(([key, v]) => ({
      key,
      // 标签优先取后端回写值; 缺失时按该模型类型的能力项反查(image_edit 等子能力不在顶层键中)
      label:
        v.label
        || capabilityOptionsFor[config?.model_type ?? '']?.find(c => c.key === key)?.label
        || key,
      ok: !!v.ok,
      detail: v.detail || '',
      error: v.error || '',
    }))

interface ModelConfigCreate extends ModelConfigBase {
  model: string; // 必填字段
}

interface ModelConfigUpdate {
  model_type?: ModelType;
  server_type?: ModelServerType;
  model?: string;
  url?: string;
  api_key?: string;
  /** 归属范围(public=所有人可见, dept=本部门可见, user=仅本人可见) */
  scope?: ModelScope;
  /** 归属部门ID(scope=dept 时服务端自动填充) */
  dept_id?: string;
  /** 是否为默认公共模型 */
  is_default?: boolean;
  /** 是否生效(不生效时灰色显示且不可用) */
  is_active?: boolean;
  /** 显示名称(区分同名模型) */
  display_name?: string;
  pay_in?: number;
  pay_out?: number;
  input_tokens?: number;
  out_tokens?: number;
  temperature?: number;
  timeout?: number;
  no_think?: boolean;
  extra?: Record<string, any>;
}

/** 扩展配置常用键预设(key/默认值/注释), "添加配置"下拉时可选 */
interface ExtraPresetOption {
  key: string
  value: string
  comment: string
}

/** 各模型类型的常用扩展键(值为编辑文本, 数字/布尔按 JSON 语义解析) */
const extraPresetsByType: Record<string, ExtraPresetOption[]> = {
  [ModelType.CHAT]: [
    { key: 'region_name', value: 'us-east-1', comment: 'AWS 区域(aws 方案)' },
    { key: 'aws_access_key_id', value: '', comment: 'AWS 访问密钥 ID(aws 方案)' },
  ],
  [ModelType.EMBEDDINGS]: [
    { key: 'timeout', value: '60', comment: '单次调用超时秒数' },
  ],
  [ModelType.RERANK]: [
    { key: 'score_threshold', value: '0.5', comment: '相关性过滤阈值(统一按 0~1 归一)' },
    { key: 'score_min', value: '0', comment: '原始分数量纲下限(gte/Qwen 系为 0)' },
    { key: 'score_max', value: '1', comment: '原始分数量纲上限(jina 系为 0.5)' },
  ],
  [ModelType.IMAGE]: [
    { key: 'size', value: '1024x1024', comment: '默认出图尺寸(宽x高)' },
    { key: 'n', value: '1', comment: '默认出图张数(1~4)' },
    { key: 'negative_prompt', value: '', comment: '反向提示词' },
    { key: 'prompt_extend', value: 'true', comment: '提示词智能改写(true/false)' },
    { key: 'watermark', value: 'false', comment: '是否添加水印(true/false)' },
    { key: 'timeout', value: '180', comment: '单次生图超时秒数' },
  ],
  [ModelType.ASR]: [
    { key: 'protocol', value: 'dashscope', comment: '上游协议(dashscope/openai)' },
    { key: 'language', value: 'zh', comment: '语种提示(如 zh/en)' },
    { key: 'enable_itn', value: 'true', comment: '逆文本正则化(数字/标点)' },
    { key: 'sample_rate', value: '16000', comment: '音频采样率(Hz)' },
    { key: 'ws_url', value: 'wss://', comment: '流式识别 WebSocket 地址' },
  ],
  [ModelType.TTS]: [
    { key: 'protocol', value: 'dashscope', comment: '上游协议(dashscope/openai)' },
    { key: 'voice', value: 'longxiaochun', comment: '音色 ID(如 longxiaochun)' },
    { key: 'ws_url', value: 'wss://', comment: '流式合成 WebSocket 地址' },
  ],
  [ModelType.OCR]: [
    { key: 'protocol', value: 'dashscope', comment: '上游协议(dashscope/openai)' },
    { key: 'prompt', value: '请提取图片中的全部文字', comment: '识别指令(整图纯文本, 无坐标框)' },
    { key: 'poll_timeout', value: '120', comment: '异步识别轮询超时秒数' },
  ],
}

/** 按模型类型取扩展配置常用键预设 */
const extraPresetsFor = (modelType: ModelType | string): ExtraPresetOption[] =>
  extraPresetsByType[modelType] ?? []

export {
  ModelServerType,
  ModelType,
  ModelScope,
  modelScopeOptions,
  scopeShortLabel,
  modelMainLabel,
  modelKeyLabel,
  modelTypeOptions,
  modelTypeTagType,
  API_SERVER_OPTIONS,
  serverTypeOptionsFor,
  modelTypeLabel,
  serverTypeLabel,
  extraPresetsFor,
  capabilityOptionsFor,
  testedCapabilities,
  type ExtraPresetOption,
  type ModelConfigBase,
  type ModelConfig,
  type ModelConfigCreate,
  type ModelConfigUpdate,
  type ModelCapabilityResult,
  type RerankScoreSuggest,
  type ModelTestResponse,
  type ModelCustomTestItem,
  type ModelCustomTestResponse,
  type ModelMediaTestResponse,
  type ModelImageResultItem,
  type ModelImageTestResponse,
}
