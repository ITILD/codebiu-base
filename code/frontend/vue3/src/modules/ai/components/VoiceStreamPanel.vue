<template>
  <!-- 实时录音流式识别面板 -->
  <div flex flex-col gap-4>
    <div flex flex-wrap items-center gap-3>
      <el-button
        :type="recording ? 'danger' : 'primary'"
        :icon="recording ? VideoPause : Microphone"
        @click="recording ? stopRecording() : startRecording()"
      >
        {{ recording ? '停止录音' : '开始录音' }}
      </el-button>
      <!-- 脉冲点有意用 bg-white: 位于 danger 红色实底标签内, 白色才能保证对比度, 不映射 note-* -->
      <el-tag v-if="recording" type="danger" effect="dark" flex items-center gap-1>
        <span inline-block w-2 h-2 bg-white rounded-full animate-pulse></span>
        录音中
      </el-tag>
      <el-button v-if="partialText || finalText" text @click="clearAsrStream">
        清空
      </el-button>
    </div>

    <el-alert
      v-if="recording"
      title="请允许浏览器使用麦克风权限"
      type="info"
      :closable="false"
      show-icon
    />

    <div mt-2>
      <div font-bold mb-2>实时识别</div>
      <div
        p-3
        bg-note-paper
        border
        border-note
        rounded
        min-h-24
        text-sm
        leading-relaxed
        whitespace-pre-wrap
        break-words
      >
        <span>{{ finalText }}</span>
        <span v-if="partialText" text-note-green>{{ partialText }}</span>
        <span
          v-if="recording"
          inline-block w-2 h-5 ml-1 bg-current opacity-70 animate-blink align-middle
        ></span>
        <span v-if="!recording && !finalText && !partialText" text-note-sub>
          点击"开始录音"后说话，识别结果将实时显示
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { Microphone, VideoPause } from '@element-plus/icons-vue'
import { buildAsrStreamUrl } from '../api/voice'
import type { VoiceEngine } from '../types/voice'

// 组件属性定义
interface Props {
  /** 语音引擎(空串=自动: 后端按 model_config 表解析默认方案) */
  engine: VoiceEngine
}

const props = defineProps<Props>()

// ============ ASR 实时录音流式状态(组件内部自持) ============
const recording = ref(false)
const partialText = ref('')
const finalText = ref('')

let mediaStream: MediaStream | null = null
let audioCtx: AudioContext | null = null
let sourceNode: MediaStreamAudioSourceNode | null = null
let processorNode: ScriptProcessorNode | null = null
let silentGain: GainNode | null = null
let ws: WebSocket | null = null

/** 清空实时识别文本 */
const clearAsrStream = () => {
  partialText.value = ''
  finalText.value = ''
}

/** 开始录音: 采集麦克风 PCM 并经 WebSocket 推流识别 */
const startRecording = async () => {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true },
    })
  } catch (e) {
    ElMessage.error('无法访问麦克风: ' + (e as Error).message)
    return
  }

  partialText.value = ''
  finalText.value = ''
  recording.value = true

  audioCtx = new AudioContext()
  sourceNode = audioCtx.createMediaStreamSource(mediaStream)
  processorNode = audioCtx.createScriptProcessor(4096, 1, 1)
  // 静音输出节点，保持 ScriptProcessor 持续触发且不产生回声
  silentGain = audioCtx.createGain()
  silentGain.gain.value = 0

  ws = new WebSocket(buildAsrStreamUrl(props.engine))
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    processorNode!.onaudioprocess = (e: AudioProcessingEvent) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      const input = e.inputBuffer.getChannelData(0)
      const downsampled = downsampleBuffer(input, audioCtx!.sampleRate, 16000)
      const pcm16 = floatTo16BitPCM(downsampled)
      ws.send(pcm16)
    }
    sourceNode!.connect(processorNode!)
    processorNode!.connect(silentGain!)
    silentGain!.connect(audioCtx!.destination)
  }

  ws.onmessage = (ev: MessageEvent) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.is_final) {
        if (msg.text) finalText.value += msg.text
        partialText.value = ''
      } else {
        partialText.value = msg.text || ''
      }
    } catch {
      /* ignore parse error */
    }
  }

  ws.onerror = () => {
    ElMessage.error('识别连接异常')
    stopRecording()
  }

  ws.onclose = () => {
    /* connection closed */
  }
}

/** 停止录音: 发送 EOS 并释放音频链路资源 */
const stopRecording = () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('EOS')
  }
  try {
    ws?.close()
  } catch {
    /* ignore */
  }
  ws = null

  if (processorNode) {
    processorNode.disconnect()
    processorNode.onaudioprocess = null
  }
  if (sourceNode) sourceNode.disconnect()
  if (silentGain) silentGain.disconnect()
  if (audioCtx) {
    audioCtx.close()
    audioCtx = null
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop())
    mediaStream = null
  }
  processorNode = null
  sourceNode = null
  silentGain = null
  recording.value = false
}

// ============ 音频工具函数(仅本面板使用) ============
/** 降采样(简单均值抽取, fromRate -> toRate) */
const downsampleBuffer = (buffer: Float32Array, fromRate: number, toRate: number): Float32Array => {
  if (toRate >= fromRate) return buffer
  const ratio = fromRate / toRate
  const newLen = Math.round(buffer.length / ratio)
  const result = new Float32Array(newLen)
  let offsetResult = 0
  let offsetBuffer = 0
  while (offsetResult < newLen) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio)
    let accum = 0
    let count = 0
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i]
      count++
    }
    result[offsetResult] = count > 0 ? accum / count : 0
    offsetResult++
    offsetBuffer = nextOffsetBuffer
  }
  return result
}

/** Float32 采样转 16bit PCM(小端) */
const floatTo16BitPCM = (input: Float32Array): ArrayBuffer => {
  const buffer = new ArrayBuffer(input.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < input.length; i++) {
    let s = Math.max(-1, Math.min(1, input[i]))
    s = s < 0 ? s * 0x8000 : s * 0x7fff
    view.setInt16(i * 2, s, true)
  }
  return buffer
}

// ============ 清理 ============
// 卸载时停止录音并释放资源
onUnmounted(() => {
  if (recording.value) stopRecording()
})
</script>
