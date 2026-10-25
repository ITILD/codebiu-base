<template>
  <!-- 模型测试对话框: 预设测试(打开自动运行) + 自定义测试 -->
  <el-dialog v-model="dialogVisible" :title="`模型测试 - ${testTargetName}`" width="90%" class="max-w-[640px]">
    <div class="flex flex-col gap-4">
      <!-- ===== 自定义测试区(按模型类型提供自定义输入, 单次真实调用) =====
           视觉顺序排在预设测试之后(order-2), 打开对话框先看"模型是否可用" -->
      <div class="order-2 rounded border border-note p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-bold text-note">自定义测试</span>
          <span class="text-xs text-note-sub">{{ customHint }}</span>
        </div>

        <!-- chat: 自定义提问 -->
        <template v-if="isType('chat')">
          <el-input v-model="chatQuestion" type="textarea" :rows="2" maxlength="2000"
            placeholder="输入问题, 真实调用一次该模型(如: 用一句话介绍你自己)" />
          <div v-if="promptLimit > 0" class="mt-1">
            <InputLimitBar :used="estimateTokens(chatQuestion)" :limit="promptLimit" label="提问" />
          </div>
          <div class="mt-2">
            <el-button type="primary" size="small" :loading="customRunning" @click="runChatTest">发送提问</el-button>
          </div>
          <div v-if="chatAnswer" class="mt-2 p-2 bg-note-tint rounded text-sm whitespace-pre-wrap break-words">
            {{ chatAnswer }}
          </div>
        </template>

        <!-- embeddings: 自定义文本向量化 -->
        <template v-else-if="isType('embeddings')">
          <el-input v-model="embText" type="textarea" :rows="2" maxlength="2000"
            placeholder="输入一段文本, 调用该模型向量化并返回维度" />
          <div class="mt-2">
            <el-button type="primary" size="small" :loading="customRunning" @click="runEmbeddingTest">向量化</el-button>
          </div>
          <div v-if="embResult" class="mt-2 text-sm text-note">{{ embResult }}</div>
        </template>

        <!-- rerank: query + 候选文档打分排序 -->
        <template v-else-if="isType('rerank')">
          <el-input v-model="rerankQuery" size="small" class="mb-2" placeholder="检索 query(如: 什么是机器学习?)" />
          <el-input v-model="rerankDocs" type="textarea" :rows="3"
            placeholder="候选文档, 每行一条(模型将按相关性打分排序)" />
          <div class="mt-2">
            <el-button type="primary" size="small" :loading="customRunning" @click="runRerankTest">打分排序</el-button>
          </div>
          <div v-if="rerankResults.length" class="mt-2 flex flex-col gap-1">
            <div v-for="(r, i) in rerankResults" :key="i"
              class="flex items-start gap-2 text-xs p-1.5 bg-note-tint rounded">
              <el-tag size="small" type="warning" class="shrink-0">#{{ i + 1 }}</el-tag>
              <span class="shrink-0 text-note-sub">原始 {{ formatScore(r.score) }} → 归一 {{ formatScore(r.normalized) }}</span>
              <span v-ellipsis class="truncate">{{ r.document }}</span>
            </div>
          </div>
        </template>

        <!-- asr: 上传音频识别 -->
        <template v-else-if="isType('asr')">
          <div class="mb-2 text-xs text-note-sub">
            也可直接使用上方「预设测试」的内置模拟音频，快速判断语音识别是否可用。
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <input ref="asrFileRef" type="file" accept="audio/*,.wav,.mp3,.m4a,.flac" class="hidden"
              @change="onAsrFileChange" />
            <el-button size="small" @click="asrFileRef?.click()">选择音频文件</el-button>
            <span v-if="asrFileName" class="text-xs text-note-sub">{{ asrFileName }}</span>
            <el-button type="primary" size="small" :disabled="!asrFile" :loading="customRunning"
              @click="runAsrTest">识别</el-button>
          </div>
          <div v-if="asrResult" class="mt-2 p-2 bg-note-tint rounded text-sm whitespace-pre-wrap break-words">
            {{ asrResult }}
          </div>
        </template>

        <!-- tts: 输入文字合成语音试听 -->
        <template v-else-if="isType('tts')">
          <el-input v-model="ttsText" type="textarea" :rows="2" maxlength="500"
            placeholder="输入一段文字, 用该模型合成语音并试听(如: 你好, 欢迎使用智能助手)" />
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <span class="text-xs text-note-sub shrink-0">语速</span>
            <el-slider v-model="ttsSpeed" :min="0.5" :max="2" :step="0.25" class="w-40" :show-tooltip="false" />
            <span class="text-xs text-note-sub w-8">{{ ttsSpeed.toFixed(2) }}x</span>
            <el-button type="primary" size="small" :loading="customRunning" @click="runTtsTest">合成试听</el-button>
          </div>
          <audio v-if="ttsAudioUrl" :src="ttsAudioUrl" controls class="mt-2 w-full" />
        </template>

        <!-- ocr: 上传图片识别(可一键生成示例图并识别) -->
        <template v-else-if="isType('ocr')">
          <div class="flex flex-wrap items-center gap-2">
            <input ref="ocrFileRef" type="file" accept="image/*" class="hidden" @change="onOcrFileChange" />
            <el-button size="small" @click="ocrFileRef?.click()">选择图片文件</el-button>
            <el-button size="small" plain :loading="customRunning" @click="runOcrSample">
              使用示例图并识别
            </el-button>
            <span v-if="ocrFileName" class="text-xs text-note-sub">{{ ocrFileName }}</span>
            <el-button type="primary" size="small" :disabled="!ocrFile" :loading="customRunning"
              @click="runOcrTest">识别</el-button>
          </div>
          <div v-if="ocrText" class="mt-2 p-2 bg-note-tint rounded text-sm whitespace-pre-wrap break-words">
            {{ ocrText }}
          </div>
        </template>

        <!-- image: 提示词(可选参考图)生成图片 -->
        <template v-else-if="isType('image')">
          <el-input v-model="imagePrompt" type="textarea" :rows="2" maxlength="2000"
            placeholder="输入提示词, 如: 一只戴墨镜的橘猫，扁平插画风格，纯色背景" />
          <div v-if="promptLimit > 0" class="mt-1">
            <InputLimitBar :used="estimateTokens(imagePrompt)" :limit="promptLimit" label="提示词" />
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <input ref="imageFileRef" type="file" accept="image/*" class="hidden" @change="onImageFileChange" />
            <el-button size="small" @click="imageFileRef?.click()">选择参考图(可选)</el-button>
            <span v-if="imageRefName" class="text-xs text-note-sub">{{ imageRefName }}</span>
            <el-button v-if="imageRefName" size="small" link type="danger" @click="clearImageRef">移除</el-button>
          </div>
          <!-- 参考图体积: 超 10MB 已自动压缩, 仍超限则拦截 -->
          <div v-if="imageRefMeta" class="mt-1">
            <InputLimitBar
              :used="imageRefMeta.bytes"
              :limit="MAX_REFERENCE_IMAGE_BYTES"
              unit="bytes"
              :label="`参考图 ${imageRefMeta.width}×${imageRefMeta.height}`"
            />
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <span class="text-xs text-note-sub shrink-0">尺寸</span>
            <el-select v-model="imageSize" class="!w-36" size="small">
              <el-option v-for="s in IMAGE_SIZE_OPTIONS" :key="s" :label="s" :value="s" />
            </el-select>
            <span class="text-xs text-note-sub shrink-0">张数</span>
            <el-input-number v-model="imageCount" :min="1" :max="4" size="small" controls-position="right" class="!w-24" />
            <el-button type="primary" size="small" :loading="customRunning" @click="runImageTest">
              {{ imageRefDataUrl ? '图生图' : '文生图' }}
            </el-button>
          </div>
          <div v-if="imageResults.length" class="mt-2 grid grid-cols-2 gap-2">
            <a v-for="(img, i) in imageResults" :key="i" :href="img.url" target="_blank" rel="noopener"
              class="block rounded overflow-hidden border border-note" :title="img.revised_prompt || '点击查看原图'">
              <img :src="img.url" :alt="`生成结果 ${i + 1}`" class="w-full h-auto object-cover" />
            </a>
          </div>
        </template>

        <!-- 其他类型: 不支持单独测试 -->
        <div v-else class="text-xs text-note-sub">该模型类型暂不支持单独测试</div>

        <!-- 单独测试失败提示 -->
        <div v-if="customError" class="mt-2">
          <el-alert type="error" :title="customError" :closable="false" class="!py-1" />
        </div>
      </div>

      <!-- ===== 预设测试区(打开对话框自动运行: 按模型类型执行预定用例, 判断当前模型是否可用) ===== -->
      <div class="order-1 rounded border border-note p-3">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div class="flex items-center gap-2">
            <span class="text-sm font-bold text-note">预设测试</span>
            <el-tag size="small" type="info" effect="plain">打开自动运行</el-tag>
          </div>
          <el-button type="primary" size="small" plain :loading="capabilityRunning" @click="runAllCapabilities">
            {{ capabilityRunning ? '检测中…' : '重新检测' }}
          </el-button>
        </div>

        <!-- 可用性结论: 直观回答"当前模型是否好用" -->
        <div class="mb-2 flex flex-wrap items-center gap-2 rounded bg-note-soft/60 px-2.5 py-2">
          <el-tag :type="availability.type" size="small">{{ availability.label }}</el-tag>
          <span v-if="testResults.length" class="text-xs text-note-sub">
            {{ passedCount }}/{{ testResults.length }} 项通过
          </span>
          <span v-else class="text-xs text-note-sub">正在按模型类型准备预定用例…</span>
        </div>

        <div v-for="item in testResults" :key="item.capability"
          class="flex items-start gap-2 py-2 border-b border-note-glass last:border-b-0">
          <el-tag :type="item.ok ? 'success' : 'danger'" size="small" class="shrink-0">
            {{ item.ok ? '通过' : '失败' }}
          </el-tag>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-sm text-note">{{ item.label }}</span>
              <span v-if="item.elapsed" class="text-xs text-note-sub">{{ item.elapsed }}s</span>
            </div>
            <div class="text-xs text-note-sub break-all">
              {{ item.ok ? (item.detail || '测试通过') : (item.error || '测试未通过') }}
            </div>
            <!-- rerank 分数范围检测建议: 一键应用 -->
            <div v-if="item.suggest?.need_fix" class="mt-2">
              <el-alert type="warning" :closable="false" class="!py-1">
                <template #title>
                  <div class="flex flex-wrap items-center gap-2">
                    <span>
                      检测到分数范围 [{{ item.suggest.observed_min }}, {{ item.suggest.observed_max }}]
                      与当前配置 [{{ item.suggest.configured_min }}, {{ item.suggest.configured_max }}] 不符，
                      score 过滤会失真
                    </span>
                    <el-button size="small" type="warning" :loading="applyingSuggest"
                      @click="applyScoreSuggest(item.suggest!)">
                      应用建议范围
                    </el-button>
                  </div>
                </template>
              </el-alert>
            </div>
          </div>
        </div>
        <div v-if="!testResults.length" class="text-sm text-note-sub">
          尚未开始检测，点击「重新检测」立即按预设用例验证当前模型。
        </div>
      </div>
    </div>
    <template #footer>
      <el-button type="primary" @click="dialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import {
  testAsrModel,
  testImageModel,
  testModelCapability,
  testModelCustom,
  testOcrModel,
  testTtsModel,
  updateModelConfig,
} from '../api/model_config'
import {
  modelMainLabel,
  ModelType,
  type ModelConfig,
  type ModelCapabilityResult,
  type ModelCustomTestItem,
  type ModelImageResultItem,
  type ModelTestResponse,
  type RerankScoreSuggest,
} from '../types/model_config'
import { ElMessage } from 'element-plus'
import InputLimitBar from './InputLimitBar.vue'
import {
  compressReferenceImage,
  estimateTokens,
  formatBytes,
  MAX_REFERENCE_IMAGE_BYTES,
} from '../utils/limits'

// ################ 组件事件 ################
const emit = defineEmits<{
  /** 已应用 rerank 分数范围建议(父组件同步本地行数据) */
  suggestApplied: [payload: { modelId: string, suggest: RerankScoreSuggest, capabilities: ModelCapabilityResult[] }]
  /** 单独测试完成(父组件刷新能力标签) */
  capabilityUpdated: [payload: { modelId: string, capabilities: ModelCapabilityResult[] }]
}>()

// ################ 对话框与测试目标 ################
const dialogVisible = ref(false)
const testTargetName = ref('')
const applyingSuggest = ref(false)
/** 当前测试目标行(应用建议时读取 extra 合并分数范围) */
let currentRow: ModelConfig | null = null
/** 当前目标模型的输入 token 上限(0=未知, 展示与拦截用) */
const promptLimit = ref(0)

/** 是否为目标模型类型(模板分区渲染用) */
const isType = (type: string) => currentRow?.model_type === type

/** 按类型的单独测试提示文案 */
const customHint = computed(() => {
  const hints: Record<string, string> = {
    [ModelType.CHAT]: '真实调用一次模型',
    [ModelType.EMBEDDINGS]: '真实调用一次向量化',
    [ModelType.RERANK]: '真实调用一次打分排序',
    [ModelType.ASR]: '上传音频真实识别一次',
    [ModelType.TTS]: '输入文字合成语音试听',
    [ModelType.OCR]: '上传图片真实识别一次',
    [ModelType.IMAGE]: '输入提示词真实出图(可传参考图)',
  }
  const t = currentRow?.model_type ?? ''
  return hints[t] ?? '该类型暂不支持自定义测试'
})

/** 分数格式化(保留4位小数, 异常值原样返回) */
const formatScore = (v?: number) => (typeof v === 'number' && isFinite(v) ? v.toFixed(4) : '-')

// ################ 预设测试结果(按模型类型执行预定用例) ################
const testResults = ref<ModelCapabilityResult[]>([])
const capabilityRunning = ref(false)

/** 预设用例通过数 */
const passedCount = computed(() => testResults.value.filter((item) => item.ok).length)

/**
 * 模型可用性结论(直接回答"当前模型是否好用")
 * - 全部通过: 模型可用
 * - 部分通过: 部分能力异常
 * - 全部失败: 模型不可用
 */
const availability = computed<{ type: 'success' | 'warning' | 'danger' | 'info', label: string }>(() => {
  if (capabilityRunning.value && !testResults.value.length) return { type: 'info', label: '检测中' }
  if (!testResults.value.length) return { type: 'info', label: '尚未检测' }
  const passed = passedCount.value
  if (passed === testResults.value.length) return { type: 'success', label: '模型可用' }
  if (passed === 0) return { type: 'danger', label: '模型不可用' }
  return { type: 'warning', label: '部分能力异常' }
})

/**
 * 打开测试对话框
 * @param row 目标模型行(展示名称/类型分区/应用建议时使用)
 * @param results 能力测试结果列表(由父组件发起测试后传入, 可为空)
 */
const open = (row: ModelConfig, results: ModelCapabilityResult[] = []) => {
  currentRow = row
  promptLimit.value = Number(row.input_tokens || 0)
  testTargetName.value = modelMainLabel(row)
  testResults.value = results
  resetCustomState()
  dialogVisible.value = true
  // 默认按预定用例直接检测当前模型是否好用(历史结果先展示, 随即刷新)
  runAllCapabilities()
}

/** 运行全部预设测试(结果持久化并通知父组件刷新标签) */
const runAllCapabilities = async () => {
  if (!currentRow) return
  try {
    capabilityRunning.value = true
    const res: ModelTestResponse = await testModelCapability(currentRow.id)
    testResults.value = res.capabilities
    emit('capabilityUpdated', { modelId: currentRow.id, capabilities: res.capabilities })
  }
  catch (error) {
    console.error('模型能力测试失败:', error)
    ElMessage.error('模型能力测试失败')
  }
  finally {
    capabilityRunning.value = false
  }
}

/** 一键应用 rerank 分数范围建议(写回模型配置 extra, 并通知父组件同步行数据) */
const applyScoreSuggest = async (suggest: RerankScoreSuggest) => {
  if (!currentRow || suggest.score_min === undefined || suggest.score_max === undefined) return
  try {
    applyingSuggest.value = true
    const mergedExtra = { ...(currentRow.extra ?? {}), score_min: suggest.score_min, score_max: suggest.score_max }
    await updateModelConfig(currentRow.id, { extra: mergedExtra })
    emit('suggestApplied', { modelId: currentRow.id, suggest, capabilities: [...testResults.value] })
    ElMessage.success(`已应用分数范围: ${suggest.score_min} ~ ${suggest.score_max}`)
  }
  catch (error) {
    console.error('应用分数范围建议失败:', error)
    ElMessage.error('应用分数范围建议失败')
  }
  finally {
    applyingSuggest.value = false
  }
}

// ################ 自定义测试(自定义参数单次真实调用) ################
const customRunning = ref(false)
const customError = ref('')

// chat
const chatQuestion = ref('')
const chatAnswer = ref('')
// embeddings
const embText = ref('')
const embResult = ref('')
// rerank
const rerankQuery = ref('')
const rerankDocs = ref('')
const rerankResults = ref<ModelCustomTestItem[]>([])
// asr
const asrFileRef = ref<HTMLInputElement>()
const asrFile = ref<File | null>(null)
const asrFileName = ref('')
const asrResult = ref('')
// tts
const ttsText = ref('')
const ttsSpeed = ref(1.0)
const ttsAudioUrl = ref('')
// ocr
const ocrFileRef = ref<HTMLInputElement>()
const ocrFile = ref<File | null>(null)
const ocrFileName = ref('')
const ocrText = ref('')
// image(文生图/图生图)
const IMAGE_SIZE_OPTIONS = ['512x512', '768x768', '1024x1024', '1280x1280', '2048x2048']
const imageFileRef = ref<HTMLInputElement>()
const imagePrompt = ref('')
const imageRefName = ref('')
/** 参考图 data URL(为空则走文生图) */
const imageRefDataUrl = ref('')
/** 参考图体积度量(压缩后, 用于展示已用/上限) */
const imageRefMeta = ref<{
  originalBytes: number
  bytes: number
  width: number
  height: number
  compressed: boolean
} | null>(null)
const imageSize = ref('1024x1024')
const imageCount = ref(1)
const imageResults = ref<ModelImageResultItem[]>([])

/** 重置自定义测试状态(打开对话框时预填一组可直接发送的默认用例) */
const resetCustomState = () => {
  customError.value = ''
  chatQuestion.value = '请用一句话介绍你自己'
  chatAnswer.value = ''
  embText.value = '人工智能正在改变世界'
  embResult.value = ''
  rerankQuery.value = '什么是机器学习？'
  rerankDocs.value = [
    '机器学习是人工智能的一个分支，研究如何让计算机从数据中学习。',
    '今天天气晴朗，适合出门散步。',
    '深度学习通过多层神经网络自动提取特征。',
  ].join('\n')
  rerankResults.value = []
  asrFile.value = null
  asrFileName.value = ''
  asrResult.value = ''
  ttsText.value = '你好，欢迎使用智能助手'
  ttsSpeed.value = 1.0
  if (ttsAudioUrl.value) URL.revokeObjectURL(ttsAudioUrl.value)
  ttsAudioUrl.value = ''
  ocrFile.value = null
  ocrFileName.value = ''
  ocrText.value = ''
  imagePrompt.value = '一只戴墨镜的橘猫，扁平插画风格，纯色背景'
  imageRefName.value = ''
  imageRefDataUrl.value = ''
  imageRefMeta.value = null
  imageSize.value = '1024x1024'
  imageCount.value = 1
  imageResults.value = []
}

/** chat 单独测试: 发送自定义提问 */
const runChatTest = async () => {
  if (!currentRow || !chatQuestion.value.trim()) {
    ElMessage.warning('请输入测试问题')
    return
  }
  try {
    customRunning.value = true
    customError.value = ''
    chatAnswer.value = ''
    const res = await testModelCustom({ model_id: currentRow.id, question: chatQuestion.value.trim() })
    if (res.ok) chatAnswer.value = res.answer || '(空回答)'
    else customError.value = res.error || '调用失败'
  }
  catch (e) {
    customError.value = (e as Error).message || '调用失败'
  }
  finally {
    customRunning.value = false
  }
}

/** embeddings 单独测试: 自定义文本向量化 */
const runEmbeddingTest = async () => {
  if (!currentRow || !embText.value.trim()) {
    ElMessage.warning('请输入待向量化的文本')
    return
  }
  try {
    customRunning.value = true
    customError.value = ''
    embResult.value = ''
    const res = await testModelCustom({ model_id: currentRow.id, text: embText.value.trim() })
    if (res.ok) embResult.value = res.detail || '向量化成功'
    else customError.value = res.error || '调用失败'
  }
  catch (e) {
    customError.value = (e as Error).message || '调用失败'
  }
  finally {
    customRunning.value = false
  }
}

/** rerank 单独测试: query + 候选文档打分排序 */
const runRerankTest = async () => {
  if (!currentRow || !rerankQuery.value.trim()) {
    ElMessage.warning('请输入检索 query')
    return
  }
  const docs = rerankDocs.value.split('\n').map(d => d.trim()).filter(Boolean)
  if (!docs.length) {
    ElMessage.warning('请输入至少一条候选文档')
    return
  }
  try {
    customRunning.value = true
    customError.value = ''
    rerankResults.value = []
    const res = await testModelCustom({
      model_id: currentRow.id,
      query: rerankQuery.value.trim(),
      documents: docs,
    })
    if (res.ok) rerankResults.value = res.results ?? []
    else customError.value = res.error || '调用失败'
  }
  catch (e) {
    customError.value = (e as Error).message || '调用失败'
  }
  finally {
    customRunning.value = false
  }
}

/** asr 文件选择 */
const onAsrFileChange = (e: Event) => {
  const input = e.target as HTMLInputElement
  asrFile.value = input.files?.[0] ?? null
  asrFileName.value = asrFile.value?.name ?? ''
  asrResult.value = ''
  input.value = ''
}

/** asr 单独测试: 上传音频识别 */
const runAsrTest = async () => {
  if (!currentRow || !asrFile.value) return
  try {
    customRunning.value = true
    customError.value = ''
    asrResult.value = ''
    const res = await testAsrModel(currentRow.id, asrFile.value)
    asrResult.value = res.text || '(无识别结果)'
  }
  catch (e) {
    customError.value = (e as Error).message || '识别失败'
  }
  finally {
    customRunning.value = false
  }
}

/** tts 单独测试: 文本合成语音并生成试听 URL */
const runTtsTest = async () => {
  if (!currentRow || !ttsText.value.trim()) {
    ElMessage.warning('请输入待合成文本')
    return
  }
  try {
    customRunning.value = true
    customError.value = ''
    if (ttsAudioUrl.value) URL.revokeObjectURL(ttsAudioUrl.value)
    ttsAudioUrl.value = ''
    const blob = await testTtsModel(currentRow.id, ttsText.value.trim(), ttsSpeed.value)
    ttsAudioUrl.value = URL.createObjectURL(blob)
  }
  catch (e) {
    customError.value = (e as Error).message || '合成失败'
  }
  finally {
    customRunning.value = false
  }
}

/** ocr 文件选择 */
const onOcrFileChange = (e: Event) => {
  const input = e.target as HTMLInputElement
  ocrFile.value = input.files?.[0] ?? null
  ocrFileName.value = ocrFile.value?.name ?? ''
  ocrText.value = ''
  input.value = ''
}

/** ocr 单独测试: 上传图片识别 */
const runOcrTest = async () => {
  if (!currentRow || !ocrFile.value) return
  try {
    customRunning.value = true
    customError.value = ''
    ocrText.value = ''
    const res = await testOcrModel(currentRow.id, ocrFile.value)
    ocrText.value = res.text || '(无识别结果)'
  }
  catch (e) {
    customError.value = (e as Error).message || '识别失败'
  }
  finally {
    customRunning.value = false
  }
}

/**
 * ocr 示例图: 用 Canvas 现画一张带文字的图片并立即识别
 * 无需用户准备素材, 打开 OCR 模型即可验证"模型是否好用"
 */
const runOcrSample = async () => {
  const canvas = document.createElement('canvas')
  canvas.width = 640
  canvas.height = 220
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    ElMessage.error('当前浏览器不支持 Canvas, 无法生成示例图')
    return
  }
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = '#1f2937'
  ctx.font = 'bold 44px "Microsoft YaHei", "PingFang SC", sans-serif'
  ctx.fillText('OCR TEST 2026', 36, 92)
  ctx.font = '32px "Microsoft YaHei", "PingFang SC", sans-serif'
  ctx.fillText('你好，世界', 36, 156)

  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) {
    ElMessage.error('示例图生成失败, 请改用本地图片')
    return
  }
  ocrFile.value = new File([blob], 'ocr-sample.png', { type: 'image/png' })
  ocrFileName.value = '示例图 ocr-sample.png'
  ocrText.value = ''
  await runOcrTest()
}

/** image 参考图选择: 本地自动压缩到 10MB 内后转 data URL(为空则走文生图) */
const onImageFileChange = async (e: Event) => {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const result = await compressReferenceImage(file)
    if (result.bytes > MAX_REFERENCE_IMAGE_BYTES) {
      ElMessage.warning('参考图压缩后仍超过 10MB, 请换一张更小的图片')
      return
    }
    imageRefDataUrl.value = result.dataUrl
    imageRefName.value = file.name
    imageRefMeta.value = result
    imageResults.value = []
    if (result.compressed) {
      ElMessage.info(
        `参考图已自动压缩: ${formatBytes(result.originalBytes)} → ${formatBytes(result.bytes)}`
      )
    }
  } catch (error) {
    ElMessage.error((error as Error).message || '参考图读取失败')
  }
}

/** 清除参考图(回到文生图) */
const clearImageRef = () => {
  imageRefDataUrl.value = ''
  imageRefName.value = ''
  imageRefMeta.value = null
  imageResults.value = []
}

/** image 单独测试: 提示词(+可选参考图)出图 */
const runImageTest = async () => {
  if (!currentRow || !imagePrompt.value.trim()) {
    ElMessage.warning('请输入提示词')
    return
  }
  try {
    customRunning.value = true
    customError.value = ''
    imageResults.value = []
    const res = await testImageModel({
      model_id: currentRow.id,
      prompt: imagePrompt.value.trim(),
      image: imageRefDataUrl.value || undefined,
      size: imageSize.value || undefined,
      n: imageCount.value || undefined,
    })
    if (res.ok) imageResults.value = res.images ?? []
    else customError.value = res.error || '生成失败'
  }
  catch (e) {
    customError.value = (e as Error).message || '生成失败'
  }
  finally {
    customRunning.value = false
  }
}

// 关闭对话框时释放音频 URL
watch(dialogVisible, (v) => {
  if (!v && ttsAudioUrl.value) {
    URL.revokeObjectURL(ttsAudioUrl.value)
    ttsAudioUrl.value = ''
  }
})

// 供父组件调用: 打开对话框
defineExpose({ open })
</script>
