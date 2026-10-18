/**
 * 语音输入(流式 ASR)组合式函数: 采集麦克风 PCM 经 WebSocket 推流到后端实时识别
 *
 * 音频链路: getUserMedia → AudioContext → ScriptProcessor 降采样 16kHz → 16bit PCM → WS 二进制帧
 * 结果回调: onPartial(说话中间结果, 实时替换) / onFinal(定稿文本, 可多次累加)
 * 供聊天输入区(ChatComposer 语音按钮)等场景复用; 采样规格与后端 ASRStreamSession 对齐
 */
import { ref, onUnmounted } from 'vue'
import { API_PREFIX } from '@/common/api/authFetch'
import { useAuthStore } from '@/common/stores/auth'

/** 组合式函数选项(结果回调) */
interface VoiceInputHandlers {
  /** 中间识别结果(实时更新, 同一轮内整体替换) */
  onPartial?: (text: string) => void
  /** 最终定稿文本(可能多次回调, 每次为一段定稿) */
  onFinal?: (text: string) => void
  /** 错误提示(无法访问麦克风/连接异常等) */
  onError?: (message: string) => void
}

/** 构建流式 ASR WebSocket 地址(与 ai/api/voice.buildAsrStreamUrl 逻辑一致, 避免 common 反向依赖模块) */
const buildAsrStreamUrl = () => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = useAuthStore().authState.tokens.access.token
  const params = new URLSearchParams()
  if (token) params.append('token', token)
  return `${proto}//${window.location.host}${API_PREFIX}/ai/voice/asr/stream?${params.toString()}`
}

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
    const s = Math.max(-1, Math.min(1, input[i]))
    const v = s < 0 ? s * 0x8000 : s * 0x7fff
    view.setInt16(i * 2, v, true)
  }
  return buffer
}

/**
 * 语音输入组合式函数
 * @param handlers 识别结果回调(可选)
 * @returns recording 录音状态 + start/stop 控制
 */
export function useVoiceInput(handlers: VoiceInputHandlers = {}) {
  const recording = ref(false)

  let mediaStream: MediaStream | null = null
  let audioCtx: AudioContext | null = null
  let sourceNode: MediaStreamAudioSourceNode | null = null
  let processorNode: ScriptProcessorNode | null = null
  let silentGain: GainNode | null = null
  let ws: WebSocket | null = null

  /** 开始录音: 采集麦克风 PCM 并经 WebSocket 推流识别 */
  const start = async () => {
    if (recording.value) return
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true },
      })
    }
    catch (e) {
      handlers.onError?.('无法访问麦克风: ' + (e as Error).message)
      return
    }

    recording.value = true
    audioCtx = new AudioContext()
    sourceNode = audioCtx.createMediaStreamSource(mediaStream)
    processorNode = audioCtx.createScriptProcessor(4096, 1, 1)
    // 静音输出节点: 保持 ScriptProcessor 持续触发且不产生回声
    silentGain = audioCtx.createGain()
    silentGain.gain.value = 0

    ws = new WebSocket(buildAsrStreamUrl())
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      if (!processorNode || !sourceNode || !silentGain || !audioCtx) return
      const ctx = audioCtx
      processorNode.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return
        const input = e.inputBuffer.getChannelData(0)
        const downsampled = downsampleBuffer(input, ctx.sampleRate, 16000)
        ws.send(floatTo16BitPCM(downsampled))
      }
      sourceNode.connect(processorNode)
      processorNode.connect(silentGain)
      silentGain.connect(audioCtx.destination)
    }

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data) as { text?: string; is_final?: boolean }
        if (msg.is_final) {
          if (msg.text) handlers.onFinal?.(msg.text)
          handlers.onPartial?.('')
        }
        else {
          handlers.onPartial?.(msg.text || '')
        }
      }
      catch {
        /* 忽略非 JSON 消息 */
      }
    }

    ws.onerror = () => {
      handlers.onError?.('语音识别连接异常')
      stop()
    }
  }

  /** 停止录音: 发送 EOS 等待最终结果并释放音频链路资源 */
  const stop = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send('EOS')
    }
    try {
      ws?.close()
    }
    catch {
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

  // 组件卸载时停止录音并释放资源
  onUnmounted(() => {
    if (recording.value) stop()
  })

  return { recording, start, stop }
}
