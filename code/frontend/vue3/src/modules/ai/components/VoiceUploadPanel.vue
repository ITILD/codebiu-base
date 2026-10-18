<template>
  <!-- 音频上传识别面板 -->
  <div flex flex-col gap-4>
    <div flex flex-wrap items-center gap-3>
      <el-button type="primary" @click="triggerAudioInput">选择音频</el-button>
      <input
        ref="audioInputRef"
        type="file"
        hidden
        accept="audio/*"
        @change="handleAudioChange"
      />
      <span v-if="asrFile" text-note text-sm text-ellipsis max-w-60>
        {{ asrFile.name }}
      </span>
    </div>

    <audio v-if="asrAudioSrc" :src="asrAudioSrc" controls w-full />

    <el-button
      type="success"
      :loading="asrLoading"
      :disabled="!asrFile || asrLoading"
      @click="recognizeUploaded"
    >
      {{ asrLoading ? '识别中...' : '开始识别' }}
    </el-button>

    <div v-if="asrResult || asrElapsed" mt-2>
      <div flex items-center justify-between mb-2>
        <span font-bold>识别结果</span>
        <span v-if="asrElapsed" text-xs text-note-sub>
          耗时 {{ asrElapsed.toFixed(3) }}s
        </span>
      </div>
      <el-input
        v-model="asrResult"
        type="textarea"
        :rows="5"
        readonly
        placeholder="识别结果将显示在此处"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { recognizeAudio } from '../api/voice'
import type { VoiceEngine } from '../types/voice'

// 组件属性定义
interface Props {
  /** 语音引擎(空串=自动: 后端按 model_config 表解析默认方案) */
  engine: VoiceEngine
}

const props = defineProps<Props>()

// ============ ASR 上传状态(组件内部自持) ============
const audioInputRef = ref<HTMLInputElement | null>(null)
const asrFile = ref<File | null>(null)
const asrAudioSrc = ref('')
const asrLoading = ref(false)
const asrResult = ref('')
const asrElapsed = ref(0)

/** 触发文件选择 */
const triggerAudioInput = () => audioInputRef.value?.click()

/** 选择音频文件: 重置结果并生成本地预览地址 */
const handleAudioChange = (e: Event) => {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    asrFile.value = target.files[0]
    asrResult.value = ''
    asrElapsed.value = 0
    asrAudioSrc.value = URL.createObjectURL(asrFile.value)
  }
}

/** 上传识别 */
const recognizeUploaded = async () => {
  if (!asrFile.value) return
  asrLoading.value = true
  asrResult.value = ''
  try {
    const data = await recognizeAudio(asrFile.value, props.engine)
    asrResult.value = data.text
    asrElapsed.value = data.elapsed
  } catch (error) {
    ElMessage.error('识别失败: ' + (error instanceof Error ? error.message : '未知错误'))
  } finally {
    asrLoading.value = false
  }
}

// ============ 清理 ============
// 卸载时释放音频预览对象 URL
onUnmounted(() => {
  if (asrAudioSrc.value) URL.revokeObjectURL(asrAudioSrc.value)
})
</script>
