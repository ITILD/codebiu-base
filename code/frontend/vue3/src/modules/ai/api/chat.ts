/**
 * AI聊天相关的API接口
 */
import { http_base_server } from '@/common/api/http'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { streamAguiEvents } from '@/common/api/aguiStream'
import type { AguiStreamCallbacks } from '@/common/api/aguiStream'
import type {
  ChatRequest,
  ChatResponse,
  ChatStreamEvent
} from '@/common/types/chat'

/**
 * 发送聊天消息
 * @param request 聊天请求
 * @returns 聊天响应
 */
export const sendChatMessage = async (request: ChatRequest) => {
  return http_base_server.post<ChatResponse>('/ai/llm/chat', request)
}

/**
 * 批量统计文本 token 数(输入/输出/上下文历史统计, 计数口径与后端一致)
 * @param texts 待计数的文本列表(返回 counts 顺序一一对应)
 * @param modelId 可选模型配置ID(传入时同时返回该模型输入上限)
 */
export const countTokens = async (texts: string[], modelId?: string) => {
  if (texts.length === 0) return { counts: [], total: 0 }
  return http_base_server.post<{
    counts: number[]
    total: number
    limit?: number | null
    remaining?: number | null
    exceeded?: boolean
  }>('/ai/llm/token-count', { texts, model_id: modelId })
}

/**
 * 查询对话模型的输入 token 上限(未选定时取全局默认 chat 配置)
 * @param modelId 模型配置ID(可选)
 */
export const getChatInputLimit = async (modelId?: string) => {
  return http_base_server.get<{ limit: number; model: string; unit: string }>(
    '/ai/llm/input-limit',
    { params: modelId ? { model_id: modelId } : {} }
  )
}

/**
 * 流式发送聊天消息 (SSE) - 优化版
 * @param request 聊天请求
 * @param onChunk 接收数据块的回调函数
 * @param onError 错误回调函数
 * @param onComplete 完成回调函数
 * @param onController 中止控制器回调(用于页面"停止生成")
 * @param onEvent 完整事件回调(含 node_name/stream_event_type, 供过程区块分组)
 */
export const sendChatMessageStream = async (
  request: ChatRequest,
  onChunk: (content: string) => void,
  onError?: (error: string) => void,
  onComplete?: () => void,
  onController?: (controller: AbortController) => void,
  onEvent?: (event: ChatStreamEvent) => void
) => {
  const controller = new AbortController()
  // 立即交给调用方, 供流式期间中止
  onController?.(controller)
  await fetchEventSource(`/base_server/ai/llm/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(request),
    signal: controller.signal,
    onmessage: (event) => {
      try {
        const parsed = JSON.parse(event.data) as ChatStreamEvent

        if (parsed.status === 'error') {
          onError?.(parsed.content || '未知错误')
          return
        }

        // 有内容即回调(含纯空白块: 空行/缩进是格式的一部分, trim 会丢换行)
        if (parsed.content) {
          onChunk(parsed.content)
        }

        // 透传完整事件(供页面按事件类型分组过程区块)
        onEvent?.(parsed)

        if (parsed.status === 'end') {
          onComplete?.()
        }
      } catch (e) {
        console.warn('解析SSE数据失败:', e)
      }
    },
    onerror: (error) => {
      console.error('流式请求失败:', error)
      onError?.(error.message || '请求失败')
      throw error
    },
    onclose: () => {
      onComplete?.()
    }
  })
  return controller
}

/**
 * 流式发送聊天消息 (AG-UI 协议 SSE)
 * 事件为 AG-UI 标准事件流(TEXT_MESSAGE / REASONING 等), 由 useAguiMessages 聚合
 * @param request 聊天请求(自动附带 event_protocol: 'agui')
 * @param callbacks 事件回调组
 */
export const sendChatMessageAguiStream = async (
  request: ChatRequest,
  callbacks: AguiStreamCallbacks
) => {
  return streamAguiEvents(
    '/base_server/ai/llm/chat',
    { ...request, event_protocol: 'agui' },
    callbacks
  )
}

/**
 * 清除模型缓存（测试用）
 * @param model_id 模型ID(为空清除全部)
 */
export const clearModelCache = async (model_id?: string) => {
  const url = model_id ? `/ai/llm/cache/${model_id}` : '/ai/llm/cache'
  return http_base_server.delete<void>(url)
}

/**
 * 校验模型配置
 * @param modelConfig 模型配置
 * @returns 校验结果
 */
export const checkModelConfig = async (modelConfig: any) => {
  return http_base_server.post<{ message: string }>('/ai/llm/check-config', modelConfig)
}
