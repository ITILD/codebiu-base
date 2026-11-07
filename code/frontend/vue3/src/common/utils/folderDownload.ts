// src/common/utils/folderDownload.ts
// 把生成文件保存到浏览器本地: 优先 File System Access API 选择目录写入文件树,
// 不支持时(如 Firefox/Safari)退化为 ZIP 打包下载(store 模式, 不压缩)

/** 待保存文件(路径为项目相对路径, 如 code/backend/server_py/src/...) */
export interface FolderFile {
  path: string
  content: string
}

/** Chromium 系浏览器的目录选择器(TS 内置 lib 未声明, 这里补充类型) */
type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options?: {
    id?: string
    mode?: 'read' | 'readwrite'
  }) => Promise<FileSystemDirectoryHandle>
}

/** 当前浏览器是否支持选择本地目录 */
export function supportsDirectoryPicker(): boolean {
  return typeof window !== 'undefined' && typeof (window as DirectoryPickerWindow).showDirectoryPicker === 'function'
}

/**
 * 弹出目录选择器
 * 必须在用户手势(点击)中同步调用, 否则会抛出 SecurityError
 *
 * @param id 目录选择器的记忆标识
 * @returns 目录句柄; 用户取消返回 null
 */
export async function pickSaveDirectory(id = 'codegen-output'): Promise<FileSystemDirectoryHandle | null> {
  const picker = (window as DirectoryPickerWindow).showDirectoryPicker
  if (!picker) return null
  try {
    return await picker({ id, mode: 'readwrite' })
  } catch (error) {
    // 用户取消不算异常
    if (error instanceof DOMException && error.name === 'AbortError') return null
    throw error
  }
}

/**
 * 按相对路径把文件写入所选目录(自动创建多级子目录)
 *
 * @param root 目录句柄
 * @param files 待写入文件
 * @returns 写入文件数量
 */
export async function writeFilesToDirectory(
  root: FileSystemDirectoryHandle,
  files: FolderFile[],
): Promise<number> {
  let count = 0
  for (const file of files) {
    const segments = file.path.split('/').filter(Boolean)
    if (!segments.length || segments.some((segment) => segment === '.' || segment === '..')) {
      continue
    }
    let dir = root
    for (const segment of segments.slice(0, -1)) {
      dir = await dir.getDirectoryHandle(segment, { create: true })
    }
    const handle = await dir.getFileHandle(segments[segments.length - 1], { create: true })
    const writable = await handle.createWritable()
    await writable.write(file.content)
    await writable.close()
    count += 1
  }
  return count
}

/* ============ ZIP 打包(store 模式) ============ */

/** CRC32 查表(首次使用时构建) */
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let i = 0; i < 256; i += 1) {
    let value = i
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
    }
    table[i] = value >>> 0
  }
  return table
})()

/** 计算字节数组的 CRC32(ZIP 校验用) */
function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i += 1) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

/** 写入小端 16 位整数 */
function setUint16(target: Uint8Array, offset: number, value: number): void {
  target[offset] = value & 0xff
  target[offset + 1] = (value >>> 8) & 0xff
}

/** 写入小端 32 位整数 */
function setUint32(target: Uint8Array, offset: number, value: number): void {
  target[offset] = value & 0xff
  target[offset + 1] = (value >>> 8) & 0xff
  target[offset + 2] = (value >>> 16) & 0xff
  target[offset + 3] = (value >>> 24) & 0xff
}

/**
 * 生成 ZIP Blob(仅存储, 无压缩)
 * 浏览器不支持目录选择时的兜底方案, 避免引入额外依赖
 */
function buildZipBlob(files: FolderFile[]): Blob {
  const encoder = new TextEncoder()
  const now = new Date()
  // DOS 时间格式: 秒精度为 2 秒
  const time = ((now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1)) & 0xffff
  const date = (((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate()) & 0xffff
  // UTF-8 文件名标志位
  const FLAG_UTF8 = 0x0800

  const localParts: BlobPart[] = []
  const centralParts: BlobPart[] = []
  let offset = 0

  for (const file of files) {
    const nameBytes = encoder.encode(file.path)
    const dataBytes = encoder.encode(file.content)
    const crc = crc32(dataBytes)

    const local = new Uint8Array(30 + nameBytes.length)
    setUint32(local, 0, 0x04034b50)
    setUint16(local, 4, 20) // 解压所需版本
    setUint16(local, 6, FLAG_UTF8)
    setUint16(local, 8, 0) // 存储方式
    setUint16(local, 10, time)
    setUint16(local, 12, date)
    setUint32(local, 14, crc)
    setUint32(local, 18, dataBytes.length)
    setUint32(local, 22, dataBytes.length)
    setUint16(local, 26, nameBytes.length)
    setUint16(local, 28, 0)
    local.set(nameBytes, 30)
    localParts.push(local, dataBytes)

    const central = new Uint8Array(46 + nameBytes.length)
    setUint32(central, 0, 0x02014b50)
    setUint16(central, 4, 20) // 创建版本
    setUint16(central, 6, 20) // 解压所需版本
    setUint16(central, 8, FLAG_UTF8)
    setUint16(central, 10, 0)
    setUint16(central, 12, time)
    setUint16(central, 14, date)
    setUint32(central, 16, crc)
    setUint32(central, 20, dataBytes.length)
    setUint32(central, 24, dataBytes.length)
    setUint16(central, 28, nameBytes.length)
    setUint16(central, 30, 0)
    setUint16(central, 32, 0)
    setUint16(central, 34, 0)
    setUint16(central, 36, 0)
    setUint32(central, 38, 0)
    setUint32(central, 42, offset)
    central.set(nameBytes, 46)
    centralParts.push(central)

    offset += local.length + dataBytes.length
  }

  const centralSize = centralParts.reduce((size, part) => size + (part as Uint8Array).length, 0)
  const end = new Uint8Array(22)
  setUint32(end, 0, 0x06054b50)
  setUint16(end, 4, 0)
  setUint16(end, 6, 0)
  setUint16(end, 8, files.length)
  setUint16(end, 10, files.length)
  setUint32(end, 12, centralSize)
  setUint32(end, 16, offset)
  setUint16(end, 20, 0)

  return new Blob([...localParts, ...centralParts, end], { type: 'application/zip' })
}

/** 以 ZIP 形式触发下载 */
export function downloadFilesAsZip(files: FolderFile[], zipName: string): void {
  const url = URL.createObjectURL(buildZipBlob(files))
  const link = document.createElement('a')
  link.href = url
  link.download = zipName
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  setTimeout(() => {
    if (link.parentNode) document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }, 1000)
}
