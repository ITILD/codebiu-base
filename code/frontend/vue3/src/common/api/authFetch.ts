/**
 * 自动携带会话令牌的原生 fetch 助手 —— 全局共享
 *
 * 覆盖统一请求客户端(http_base_server)不适用的场景:
 *   - 流式读取(SSE/PCM 流)
 *   - Blob 下载
 *   - WebSocket 之外需要手动控制 Response 的场景
 */
import { useAuthStore } from '@/common/stores/auth'

/** 后端接口前缀(与 common/api/http.ts 中 http_base_server 一致) */
export const API_PREFIX = '/base_server'

/** 会话访问令牌请求头(未登录返回空对象) */
export const authHeader = (): Record<string, string> => {
  const token = useAuthStore().authState.tokens.access.token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * 自动携带会话令牌的原生 fetch
 * @param url 完整 URL(可用 API_PREFIX 拼接)
 * @param init fetch 初始化参数(init.headers 优先级高于自动令牌头)
 */
export const authFetch = (url: string, init: RequestInit = {}): Promise<Response> => {
  return fetch(url, {
    ...init,
    headers: {
      ...authHeader(),
      ...init.headers,
    },
  })
}
