<template>
  <!-- 语音合成 TTS 面板 -->
  <div flex flex-col gap-4>
    <el-input
      v-model="ttsText"
      type="textarea"
      :rows="5"
      placeholder="请输入需要合成的文本..."
    />

    <div flex flex-wrap items-center gap-4>
      <div flex items-center gap-2>
        <span text-sm>说话人:</span>
        <el-input-number v-model="ttsSpeaker" :min="0" :max="10" size="small" />
      </div>
      <div flex items-center gap-2 flex-1 min-w-40>
        <span text-sm>语速:</span>
        <el-slider v-model="ttsSpeed" :min="0.5" :max="2" :step="0.1" flex-1 />
        <span text-xs text-note-sub w-10>{{ ttsSpeed.toFixed(1) }}x</span>
      </div>
    </div>

    <div flex flex-wrap gap-3>
      <el-button
        type="primary"
        :loading="ttsStreaming"
        :disabled="!ttsText.trim() || ttsStreaming"
        @click="playStream"
      >
        {{ ttsStreaming ? '合成播放中...' : '流式合成并播放' }}
      </el-button>
      <el-button
        type="success"
        :loading="ttsFileLoading"
        :disabled="!ttsText.trim() || ttsFileLoading"
        @click="synthesizeFile"
      >
        {{ ttsFileLoading ? '生成中...' : '生成音频文件' }}
      </el-button>
      <el-button
        v-if="ttsFileUrl"
        tag="a"
        :href="ttsFileUrl"
        download="tts.wav"
      >
        下载 wav
      </el-button>
    </div>

    <el-progress
      v-if="ttsStreaming"
      :percentage="100"
      :indeterminate="true"
      :show-text="false"
      status="success"
    />

    <audio v-if="ttsFileUrl" :src="ttsFileUrl" controls w-full />

    <el-alert
      v-if="ttsStatus"
      :title="ttsStatus"
      :type="ttsStatusType"
      :closable="false"
      show-icon
    />
  </div>
</template>

<script setup lang="ts">
import { synthesizeAudioFile, synthesizeAudioStream } from '../api/voice'
import type { VoiceEngine } from '../types/voice'

// 组件属性定义
interface Props {
  /** 语音引擎(空串=自动: 后端按 model_config 表解析默认方案) */
  engine: VoiceEngine
}

const props = defineProps<Props>()

// ============ TTS 状态(组件内部自持) ============
const ttsText = ref('')
const ttsSpeaker = ref(0)
const ttsSpeed = ref(1.0)
const ttsStreaming = ref(false)
const ttsFileLoading = ref(false)
const ttsFileUrl = ref('')
const ttsStatus = ref('')
const ttsStatusType = ref<'success' | 'error' | 'info'>('info')

let playCtx: AudioContext | null = null

/** 流式合成并播放: PCM 分块到达即排入播放队列 */
const playStream = async () => {
  if (!ttsText.value.trim()) return
  // 停止之前的播放
  if (playCtx) {
    try {
      await playCtx.close()
    } catch {
      /* ignore */
    }
  }
  ttsStreaming.value = true
  ttsStatus.value = '正在流式合成并播放...'
  ttsStatusType.value = 'info'

  playCtx = new AudioContext()
  let nextStart = playCtx.currentTime
  let received = 0

  await synthesizeAudioStream(
    {
      text: ttsText.value,
      engine: props.engine,
      speaker: ttsSpeaker.value,
      speed: ttsSpeed.value,
    },
    (pcm: Uint8Array, sampleRate: number) => {
      if (!playCtx) return
      const float32 = int16ToFloat32(pcm)
      if (float32.length === 0) return
      received += float32.length
      const buffer = playCtx.createBuffer(1, float32.length, sampleRate)
      buffer.copyToChannel(float32, 0)
      const src = playCtx.createBufferSource()
      src.buffer = buffer
      src.connect(playCtx.destination)
      const now = playCtx.currentTime
      if (nextStart < now) nextStart = now
      src.start(nextStart)
      nextStart += float32.length / sampleRate
    },
    (error: string) => {
      ttsStatus.value = '流式合成失败: ' + error
      ttsStatusType.value = 'error'
      ttsStreaming.value = false
    },
    () => {
      ttsStatus.value = received > 0 ? '播放完成' : '未收到音频数据'
      ttsStatusType.value = received > 0 ? 'success' : 'error'
      ttsStreaming.value = false
    }
  )
}

/** 合成为完整音频文件(供下载/播放) */
const synthesizeFile = async () => {
  if (!ttsText.value.trim()) return
  ttsFileLoading.value = true
  ttsStatus.value = '正在生成音频文件...'
  ttsStatusType.value = 'info'
  if (ttsFileUrl.value) {
    URL.revokeObjectURL(ttsFileUrl.value)
    ttsFileUrl.value = ''
  }
  try {
    const blob = await synthesizeAudioFile({
      text: ttsText.value,
      engine: props.engine,
      speaker: ttsSpeaker.value,
      speed: ttsSpeed.value,
    })
    ttsFileUrl.value = URL.createObjectURL(blob)
    ttsStatus.value = '音频文件生成完成'
    ttsStatusType.value = 'success'
  } catch (error) {
    ttsStatus.value = '生成失败: ' + (error instanceof Error ? error.message : '未知错误')
    ttsStatusType.value = 'error'
  } finally {
    ttsFileLoading.value = false
  }
}

// ============ 音频工具函数(仅本面板使用) ============
/** 16bit PCM(小端)转 Float32 采样 */
const int16ToFloat32 = (input: Uint8Array): Float32Array => {
  const n = Math.floor(input.length / 2)
  const result = new Float32Array(n)
  const view = new DataView(input.buffer, input.byteOffset, input.byteLength)
  for (let i = 0; i < n; i++) {
    result[i] = view.getInt16(i * 2, true) / 32768
  }
  return result
}

// ============ 清理 ============
// 卸载时关闭播放上下文并释放音频对象 URL
onUnmounted(() => {
  if (playCtx) {
    try {
      playCtx.close()
    } catch {
      /* ignore */
    }
  }
  if (ttsFileUrl.value) URL.revokeObjectURL(ttsFileUrl.value)
})
</script>
