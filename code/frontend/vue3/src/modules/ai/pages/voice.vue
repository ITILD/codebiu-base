<template>
  <div flex flex-col h-app w-full bg-note-paper>
    <!-- 顶部引擎选择栏(方案来自 AI 服务 → 模型配置); 内阴影替代硬边线 -->
    <div class="note-edge-b" p-4 bg-note-soft>
      <div flex flex-wrap items-center gap-4>
        <span text-sm font-medium text-note>语音引擎:</span>
        <el-radio-group v-model="engine">
          <el-radio-button value="">自动(模型配置)</el-radio-button>
          <el-radio-button value="online">在线(远程API/本地vllm发布)</el-radio-button>
        </el-radio-group>
        <el-tooltip
          v-if="engine === ''"
          :content="autoEngineTip"
          placement="bottom"
          :disabled="!autoEngineTip"
        >
          <el-tag size="small" type="info" cursor-help>
            ASR: {{ asrConfigLabel }} / TTS: {{ ttsConfigLabel }}
          </el-tag>
        </el-tooltip>
        <el-link
          v-if="engine === '' && (!asrConfigLabel || !ttsConfigLabel)"
          type="primary"
          text-sm
          @click="router.push('/ai/model_config')"
        >
          去模型配置添加 asr/tts 方案
        </el-link>
        <span text-xs text-note-sub>语音模型均通过外部服务接入, 请在模型配置中添加 online 方案</span>
      </div>
    </div>

    <!-- 主体内容 -->
    <div flex-1 overflow-y-auto p-4>
      <div flex flex-col lg:flex-row gap-5 max-w-7xl mx-auto>
        <!-- ============ ASR 语音识别 ============ -->
        <el-card flex-1 min-w-0>
          <template #header>
            <div flex items-center gap-2>
              <span text-lg font-bold>🎤 语音识别 ASR</span>
              <el-tag size="small" type="success">{{ engineLabel }}</el-tag>
            </div>
          </template>

          <el-tabs v-model="asrTab">
            <!-- 音频上传(面板组件自持上传/识别状态) -->
            <el-tab-pane label="音频上传" name="upload">
              <VoiceUploadPanel :engine="engine" />
            </el-tab-pane>

            <!-- 实时录音流式(面板组件自持录音/WebSocket 状态) -->
            <el-tab-pane label="实时录音(流式)" name="stream">
              <VoiceStreamPanel :engine="engine" />
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <!-- ============ TTS 语音合成(面板组件自持合成状态) ============ -->
        <el-card flex-1 min-w-0>
          <template #header>
            <div flex items-center gap-2>
              <span text-lg font-bold>🔊 语音合成 TTS</span>
              <el-tag size="small" type="success">{{ engineLabel }}</el-tag>
            </div>
          </template>

          <VoiceTtsPanel :engine="engine" />
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { VoiceEngine } from '../types/voice'
import type { PaginationParams } from '@/common/types/common'
import type { ModelConfig } from '../types/model_config'
import { serverTypeLabel } from '../types/model_config'
import { listModelConfigs } from '../api/model_config'
import VoiceUploadPanel from '../components/VoiceUploadPanel.vue'
import VoiceStreamPanel from '../components/VoiceStreamPanel.vue'
import VoiceTtsPanel from '../components/VoiceTtsPanel.vue'

const router = useRouter()

// 共享引擎(空串=自动: 后端按 model_config 表解析默认方案)
const engine = ref<VoiceEngine>('')

// 引擎选择展示标签
const engineLabel = computed(() => (engine.value === '' ? '自动' : engine.value))

// ===== 模型配置(asr/tts 类型方案, 供自动模式解析与提示展示) =====
const asrConfigs = ref<ModelConfig[]>([])
const ttsConfigs = ref<ModelConfig[]>([])

/** 加载语音类模型配置 */
const loadVoiceConfigs = async () => {
  try {
    const [asrRes, ttsRes] = await Promise.all([
      listModelConfigs({ page: 1, size: 50, model_type: 'asr' } as PaginationParams),
      listModelConfigs({ page: 1, size: 50, model_type: 'tts' } as PaginationParams),
    ])
    asrConfigs.value = asrRes.items
    ttsConfigs.value = ttsRes.items
  }
  catch (error) {
    console.error('加载语音模型配置失败:', error)
  }
}

/** 默认(第一条)ASR 配置描述 */
const asrConfigLabel = computed(() =>
  asrConfigs.value[0]
    ? `${serverTypeLabel(asrConfigs.value[0].server_type)} · ${asrConfigs.value[0].model}`
    : '未配置')

/** 默认(第一条)TTS 配置描述 */
const ttsConfigLabel = computed(() =>
  ttsConfigs.value[0]
    ? `${serverTypeLabel(ttsConfigs.value[0].server_type)} · ${ttsConfigs.value[0].model}`
    : '未配置')

/** 自动模式提示 */
const autoEngineTip = computed(() =>
  `后端将按模型配置自动选择引擎\nASR: ${asrConfigLabel.value}\nTTS: ${ttsConfigLabel.value}`)

// ASR 当前激活 tab(上传/实时录音)
const asrTab = ref('upload')

// 页面加载时读取模型配置
onMounted(() => {
  loadVoiceConfigs()
})
</script>
