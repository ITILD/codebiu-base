<template>
  <!-- 能力测试 + 单独测试对话框 -->
  <el-dialog v-model="dialogVisible" :title="`模型测试 - ${testTargetName}`" width="90%" class="max-w-[640px]">
    <div class="flex flex-col gap-4">
      <!-- ===== 单独测试区(按模型类型提供自定义输入, 单次真实调用) ===== -->
      <div class="rounded border border-note p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-bold text-note">单独测试</span>
          <span class="text-xs text-note-sub">{{ customHint }}</span>
        </div>

        <!-- chat: 自定义提问 -->
        <template v-if="isType('chat')">
          <el-input v-model="chatQuestion" type="textarea" :rows="2" maxlength="2000"
            placeholder="输入问题, 真实调用一次该模型(如: 用一句话介绍你自己)" />
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
              <span class="truncate">{{ r.document }}</span>
            </div>
          </div>
        </template>

        <!-- asr: 上传音频识别 -->
        <template v-else-if="isType('asr')">
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

        <!-- ocr: 上传图片识别 -->
        <template v-else-if="isType('ocr')">
          <div class="flex flex-wrap items-center gap-2">
            <input ref="ocrFileRef" type="file" accept="image/*" class="hidden" @change="onOcrFileChange" />
            <el-button size="small" @click="ocrFileRef?.click()">选择图片文件</el-button>
            <span v-if="ocrFileName" class="text-xs text-note-sub">{{ ocrFileName }}</span>
            <el-button type="primary" size="small" :disabled="!ocrFile" :loading="customRunning"
              @click="runOcrTest">识别</el-button>
          </div>
          <div v-if="ocrText" class="mt-2 p-2 bg-note-tint rounded text-sm whitespace-pre-wrap break-words">
            {{ ocrText }}
          </div>
        </template>

        <!-- 其他类型: 不支持单独测试 -->
        <div v-else class="text-xs text-note-sub">该模型类型暂不支持单独测试</div>

        <!-- 单独测试失败提示 -->
        <div v-if="customError" class="mt-2">
          <el-alert type="error" :title="customError" :closable="false" class="!py-1" />
        </div>
      </div>

      <!-- ===== 能力测试区(预设用例批量冒烟, 结果持久化为能力标签) ===== -->
      <div class="rounded border border-note p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-bold text-note">能力测试</span>
          <el-button type="primary" size="small" plain :loading="capabilityRunning" @click="runAllCapabilities">
            运行全部
          </el-button>
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
        <div v-if="!testResults.length" class="text-sm text-note-sub">尚未测试, 点击"运行全部"开始</div>
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
  type ModelTestResponse,
  type RerankScoreSuggest,
} from '../types/model_config'
import { ElMessage } from 'element-plus'

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
  }
  const t = currentRow?.model_type ?? ''
  return hints[t] ?? '该类型暂不支持单独测试'
})

/** 分数格式化(保留4位小数, 异常值原样返回) */
const formatScore = (v?: number) => (typeof v === 'number' && isFinite(v) ? v.toFixed(4) : '-')

// ################ 能力测试结果(预设用例批量冒烟) ################
const testResults = ref<ModelCapabilityResult[]>([])
const capabilityRunning = ref(false)

/**
 * 打开测试对话框
 * @param row 目标模型行(展示名称/类型分区/应用建议时使用)
 * @param results 能力测试结果列表(由父组件发起测试后传入, 可为空)
 */
const open = (row: ModelConfig, results: ModelCapabilityResult[] = []) => {
  currentRow = row
  testTargetName.value = modelMainLabel(row)
  testResults.value = results
  resetCustomState()
  dialogVisible.value = true
  // 无历史结果时自动跑一次全部能力测试
  if (!results.length) runAllCapabilities()
}

/** 运行全部能力测试(结果持久化并通知父组件刷新标签) */
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

// ################ 单独测试(自定义参数单次真实调用) ################
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

/** 重置单独测试状态(打开对话框时调用, 释放旧音频 URL) */
const resetCustomState = () => {
  customError.value = ''
  chatQuestion.value = ''
  chatAnswer.value = ''
  embText.value = ''
  embResult.value = ''
  rerankQuery.value = ''
  rerankDocs.value = ''
  rerankResults.value = []
  asrFile.value = null
  asrFileName.value = ''
  asrResult.value = ''
  ttsText.value = ''
  ttsSpeed.value = 1.0
  if (ttsAudioUrl.value) URL.revokeObjectURL(ttsAudioUrl.value)
  ttsAudioUrl.value = ''
  ocrFile.value = null
  ocrFileName.value = ''
  ocrText.value = ''
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
