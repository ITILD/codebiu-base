/**
 * HTTP 错误信息提取 —— 全局共享
 *
 * 统一收敛 FastAPI 错误响应的可读化解析:
 *   - detail 为字符串: 直接使用
 *   - detail 为数组(FastAPI 422 校验错误 [{loc, msg, type}]): 拼接为可读信息
 * 供两处复用:
 *   - common/api/http.ts 的 responseInterceptor(统一请求客户端)
 *   - 原生 fetch 场景(流式/blob 下载等)的 extractHttpErrorMessage
 */

/**
 * 从错误响应体中解析 FastAPI detail 为可读信息
 * @returns 解析失败返回 null(调用方自行回退默认文案)
 */
export const parseFastApiDetail = (err: unknown): string | null => {
  if (!err || typeof err !== 'object' || !('detail' in err)) return null
  const detail = (err as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return (
      detail
        .map((item: { loc?: (string | number)[]; msg?: string }) => {
          const field = item.loc?.filter((p) => p !== 'body').join('.')
          return field ? `${field}: ${item.msg ?? ''}` : (item.msg ?? '')
        })
        .filter(Boolean)
        .join('; ') || null
    )
  }
  return null
}

/**
 * 从错误 Response 中提取可读错误信息(原生 fetch 场景用)
 * 兼容: detail 字符串 / FastAPI 422 校验错误数组; 非 JSON 响应回退状态码文案
 */
export const extractHttpErrorMessage = async (resp: Response): Promise<string> => {
  let msg = `HTTP ${resp.status}`
  try {
    msg = parseFastApiDetail(await resp.json()) ?? msg
  } catch {
    /* 非 JSON 响应, 保持默认状态码信息 */
  }
  return msg
}
