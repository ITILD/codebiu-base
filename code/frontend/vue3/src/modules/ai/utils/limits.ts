/**
 * AI 调用输入限制(前端侧): token 即时估算、体积格式化、参考图本地压缩
 *
 * 说明:
 * - token 估算仅用于输入时即时反馈, 权威计数仍以后端 /ai/llm/token-count 为准
 * - 参考图压缩与后端一致: 最长边 2048 + JPEG 重编码, 目标 < 10MB(百炼单图上限)
 */

/** 百炼生图参考图体积上限(10MB) */
export const MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
/** 参考图最长边(超过自动等比缩放) */
export const MAX_REFERENCE_IMAGE_EDGE = 2048

/**
 * 估算文本 token 数(中文 1 字≈0.67 token, 其他 4 字符≈1 token)
 * @param text 文本
 */
export const estimateTokens = (text: string): number => {
  if (!text) return 0
  const cjk = (text.match(/[\u4e00-\u9fff\u3040-\u30ff]/g) || []).length
  const rest = Math.max(0, text.length - cjk)
  return Math.ceil(cjk / 1.5 + rest / 4)
}

/**
 * 字节数格式化(1.2 MB / 356 KB)
 * @param bytes 字节数
 */
export const formatBytes = (bytes: number): string => {
  if (!bytes) return '0 B'
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

/** data URL 解码后的字节数估算(base64 4 字符≈3 字节) */
export const dataUrlBytes = (dataUrl: string): number => {
  const base64 = dataUrl.split(',')[1] || ''
  return Math.ceil((base64.length * 3) / 4)
}

/** 读取文件为 data URL */
const readFileAsDataUrl = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('图片读取失败'))
    reader.readAsDataURL(file)
  })

/** 加载 data URL 为图片对象 */
const loadImage = (src: string): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片解析失败(仅支持 PNG/JPG/WEBP)'))
    img.src = src
  })

/**
 * 参考图上传前本地压缩: 超限自动缩放 + 降质, 保证可被生图服务接受
 * @param file 用户选择的图片文件
 * @param maxBytes 允许的最大体积(默认 10MB)
 * @return data URL 与度量信息(超出且无法压到上限内时 compressed 为 true 但 bytes 仍超限)
 */
export const compressReferenceImage = async (
  file: File,
  maxBytes: number = MAX_REFERENCE_IMAGE_BYTES
): Promise<{
  dataUrl: string
  originalBytes: number
  bytes: number
  width: number
  height: number
  compressed: boolean
}> => {
  const originalBytes = file.size
  const source = await readFileAsDataUrl(file)
  // 未超限: 原样保留(避免无谓画质损失)
  if (originalBytes <= maxBytes) {
    const img = await loadImage(source).catch(() => null)
    return {
      dataUrl: source,
      originalBytes,
      bytes: originalBytes,
      width: img?.naturalWidth ?? 0,
      height: img?.naturalHeight ?? 0,
      compressed: false,
    }
  }

  const img = await loadImage(source)
  let width = img.naturalWidth
  let height = img.naturalHeight
  const scale = Math.min(1, MAX_REFERENCE_IMAGE_EDGE / Math.max(width, height))
  width = Math.round(width * scale)
  height = Math.round(height * scale)

  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('浏览器不支持图片压缩, 请换用较小图片')
  let dataUrl = ''
  let bytes = 0
  const target = Math.min(maxBytes, Math.floor(maxBytes * 0.9))
  const qualities = [0.88, 0.8, 0.72, 0.64, 0.56, 0.48, 0.4]
  for (let round = 0; round < 4; round++) {
    canvas.width = width
    canvas.height = height
    ctx.drawImage(img, 0, 0, width, height)
    for (const quality of qualities) {
      dataUrl = canvas.toDataURL('image/jpeg', quality)
      bytes = dataUrlBytes(dataUrl)
      if (bytes <= target) break
    }
    if (bytes <= target) break
    // 仍超限: 等比缩小后再压
    width = Math.max(128, Math.round(width * 0.8))
    height = Math.max(128, Math.round(height * 0.8))
  }
  return {
    dataUrl,
    originalBytes,
    bytes,
    width,
    height,
    compressed: true,
  }
}
