/**
 * ProTable 列设置持久化: 列显隐 / 列顺序 / 行密度
 *
 * 设计要点
 * - 存储键统一为 `pro-table-prefs:<tableKey>`, 同一页面可有多张表互不干扰
 * - 读取时与当前 columns 声明合并: 过滤已不存在的列、补全新增列、去重
 * - 版本迁移容错: 旧版本/脏数据/非法 JSON 一律降级为默认值, 并回写规范化结果
 * - 至少保留一列可见, 避免用户误操作后得到全空表格
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'

/** 下拉/字典选项 */
export interface ProTableColumnOption {
  label: string
  value: string | number | boolean
}

/** 表格行数据(不限定业务字段) */
export type ProTableRow = Record<string, any>

/** 列配置(页面声明, ProTable 渲染 + 列设置共用) */
export interface ProTableColumn {
  /** 字段名(同时作为列唯一标识与动态插槽名: col-<prop>) */
  prop: string
  /** 列标题 */
  label: string
  /** 固定宽度 */
  width?: string | number
  /** 最小宽度(缺省 100) */
  minWidth?: string | number
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
  /** 固定列(平板及以下自动取消固定) */
  fixed?: 'left' | 'right' | boolean
  /** 排序(透传 el-table-column) */
  sortable?: boolean | 'custom'
  /** 超长省略 + 悬浮提示(缺省开启; 显式 false 关闭, 如需要单元格内换行/多行内容的列) */
  showOverLimit?: boolean
  /** 自定义展示: 返回字符串(插槽优先级更高) */
  formatter?: (row: ProTableRow, value: any, index: number) => string
  /** 是否提供 col-<prop> 动态插槽 */
  slot?: boolean
  /** 是否参与查询栏(预留, 由页面自行渲染搜索区) */
  searchable?: boolean
  /** 查询控件类型 */
  searchType?: 'input' | 'select' | 'date'
  /** 字典类型(预留) */
  dictType?: string
  /** 是否可行内编辑 */
  editable?: boolean
  /** 行内编辑控件类型(缺省 input) */
  editor?: 'input' | 'number' | 'select' | 'switch' | 'date'
  /** 编辑器选项(editor=select 时使用) */
  options?: ProTableColumnOption[]
}

/** 行密度: 默认 / 中等 / 紧凑 */
export type ProTableDensity = 'default' | 'medium' | 'small'

/** 持久化结构 */
export interface ProTablePrefs {
  version: number
  order: string[]
  hidden: string[]
  density: ProTableDensity
}

/** 当前持久化版本(结构变更时递增, 读取逻辑做降级兼容) */
const PREFS_VERSION = 1
/** 存储键前缀 */
const PREFS_KEY_PREFIX = 'pro-table-prefs:'
const DENSITY_VALUES: ProTableDensity[] = ['default', 'medium', 'small']

/** 生成某张表的持久化键 */
export const proTablePrefsKey = (tableKey: string) => `${PREFS_KEY_PREFIX}${tableKey}`

/** 默认偏好: 列顺序按声明顺序, 全部可见, 默认密度 */
export function createDefaultPrefs(columns: ProTableColumn[]): ProTablePrefs {
  return {
    version: PREFS_VERSION,
    order: columns.map((col) => col.prop),
    hidden: [],
    density: 'default',
  }
}

/**
 * 读取并规范化偏好
 * @param tableKey 表标识
 * @param columns 当前列声明
 */
export function readProTablePrefs(tableKey: string, columns: ProTableColumn[]): ProTablePrefs {
  const fallback = createDefaultPrefs(columns)

  let raw: string | null = null
  try {
    raw = localStorage.getItem(proTablePrefsKey(tableKey))
  } catch {
    return fallback // 隐私模式等场景无法访问 localStorage
  }
  if (!raw) return fallback

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return fallback // 非法 JSON: 直接回默认
  }
  if (!parsed || typeof parsed !== 'object') return fallback

  const source = parsed as Record<string, unknown>
  const knownProps = new Set(columns.map((col) => col.prop))

  // 顺序: 过滤未知列(旧版本残留)/重复项, 再按声明顺序补全新列
  const storedOrder = Array.isArray(source.order)
    ? source.order.filter((prop): prop is string => typeof prop === 'string' && knownProps.has(prop))
    : []
  const order = [...new Set(storedOrder)]
  for (const col of columns) {
    if (!order.includes(col.prop)) order.push(col.prop)
  }

  // 隐藏列: 同样过滤未知项; 全部隐藏视为脏数据, 恢复全部可见
  const storedHidden = Array.isArray(source.hidden)
    ? source.hidden.filter((prop): prop is string => typeof prop === 'string' && knownProps.has(prop))
    : []
  const hidden = order.length > new Set(storedHidden).size ? [...new Set(storedHidden)] : []

  // 密度: 非枚举值回默认; 版本号不匹配也走上面的合并逻辑(结构向后兼容)
  const density = DENSITY_VALUES.includes(source.density as ProTableDensity)
    ? (source.density as ProTableDensity)
    : fallback.density

  return { version: PREFS_VERSION, order, hidden, density }
}

/**
 * 列设置/密度状态与操作
 * @param columns 列声明(响应式, 支持列动态变化)
 * @param tableKey 持久化标识
 */
export function useProTablePrefs(
  columns: Ref<ProTableColumn[]> | ComputedRef<ProTableColumn[]>,
  tableKey: string,
) {
  const initial = readProTablePrefs(tableKey, columns.value)
  const order = ref<string[]>([...initial.order])
  const hidden = ref<string[]>([...initial.hidden])
  const density = ref<ProTableDensity>(initial.density)

  /** 全部列(按用户顺序; 新增列自动追加到末尾) */
  const orderedColumns = computed(() => {
    const map = new Map<string, ProTableColumn>(columns.value.map((col) => [col.prop, col]))
    const list = order.value
      .map((prop) => map.get(prop))
      .filter((col): col is ProTableColumn => !!col)
    for (const col of columns.value) {
      if (!order.value.includes(col.prop)) list.push(col)
    }
    return list
  })

  /** 可见列(兜底: 若无可见列则回退为全部列) */
  const visibleColumns = computed(() => {
    const list = orderedColumns.value.filter((col) => !hidden.value.includes(col.prop))
    return list.length ? list : orderedColumns.value
  })

  /** 写入 localStorage(失败时静默降级为不持久化) */
  const persist = () => {
    try {
      localStorage.setItem(
        proTablePrefsKey(tableKey),
        JSON.stringify({
          version: PREFS_VERSION,
          order: order.value,
          hidden: hidden.value,
          density: density.value,
        } satisfies ProTablePrefs),
      )
    } catch {
      /* 配额不足/隐私模式: 忽略 */
    }
  }

  const isColumnHidden = (prop: string) => hidden.value.includes(prop)

  /** 切换列显隐(至少保留一列) */
  const toggleColumn = (prop: string) => {
    if (isColumnHidden(prop)) {
      hidden.value = hidden.value.filter((item) => item !== prop)
      persist()
      return
    }
    if (visibleColumns.value.length <= 1) return
    hidden.value = [...hidden.value, prop]
    persist()
  }

  const canMoveUp = (prop: string) => order.value.indexOf(prop) > 0

  const canMoveDown = (prop: string) => {
    const index = order.value.indexOf(prop)
    return index >= 0 && index < order.value.length - 1
  }

  /** 上移/下移一列(只交换相邻项) */
  const moveColumn = (prop: string, step: -1 | 1) => {
    const list = [...order.value]
    const from = list.indexOf(prop)
    const to = from + step
    if (from < 0 || to < 0 || to >= list.length) return
    ;[list[from], list[to]] = [list[to], list[from]]
    order.value = list
    persist()
  }

  /** 切换密度(非法值忽略) */
  const setDensity = (value: ProTableDensity) => {
    if (!DENSITY_VALUES.includes(value)) return
    density.value = value
    persist()
  }

  /** 重置为默认列顺序/全部可见/默认密度, 并清除该表本地偏好 */
  const reset = () => {
    const defaults = createDefaultPrefs(columns.value)
    order.value = defaults.order
    hidden.value = []
    density.value = defaults.density
    try {
      localStorage.removeItem(proTablePrefsKey(tableKey))
    } catch {
      /* 忽略 */
    }
  }

  // 首次读取即回写规范化结果, 完成旧版本/脏数据的迁移
  persist()

  return {
    density,
    orderedColumns,
    visibleColumns,
    isColumnHidden,
    toggleColumn,
    canMoveUp,
    canMoveDown,
    moveColumn,
    setDensity,
    reset,
  }
}
