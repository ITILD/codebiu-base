// ProTable 列设置持久化单测: 默认值合并 / 保存后读取 / 脏数据与旧版本容错 / 最少保留一列
import { beforeEach, describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  proTablePrefsKey,
  readProTablePrefs,
  useProTablePrefs,
  type ProTableColumn,
} from './useProTablePrefs'

const columns: ProTableColumn[] = [
  { prop: 'a', label: 'A' },
  { prop: 'b', label: 'B' },
  { prop: 'c', label: 'C' },
]

const storeKey = proTablePrefsKey('demo')

beforeEach(() => {
  localStorage.clear()
})

describe('useProTablePrefs', () => {
  it('无本地记录时按列声明合并默认值并回写规范结构', () => {
    const prefs = useProTablePrefs(ref(columns), 'demo')
    expect(prefs.visibleColumns.value.map((col) => col.prop)).toEqual(['a', 'b', 'c'])
    expect(prefs.density.value).toBe('default')

    const saved = JSON.parse(localStorage.getItem(storeKey) ?? '{}')
    expect(saved).toMatchObject({ version: 1, order: ['a', 'b', 'c'], hidden: [], density: 'default' })
  })

  it('列显隐/顺序/密度变更后持久化, 新实例可完整还原', () => {
    const first = useProTablePrefs(ref(columns), 'demo')
    first.toggleColumn('b') // 隐藏 b
    first.moveColumn('c', -1) // c 上移到 a 之后
    first.setDensity('small')
    expect(first.visibleColumns.value.map((col) => col.prop)).toEqual(['a', 'c'])

    const second = useProTablePrefs(ref(columns), 'demo')
    expect(second.orderedColumns.value.map((col) => col.prop)).toEqual(['a', 'c', 'b'])
    expect(second.visibleColumns.value.map((col) => col.prop)).toEqual(['a', 'c'])
    expect(second.density.value).toBe('small')
  })

  it('非法 JSON 降级为默认值', () => {
    localStorage.setItem(storeKey, '{oops')
    const prefs = useProTablePrefs(ref(columns), 'demo')
    expect(prefs.visibleColumns.value.map((col) => col.prop)).toEqual(['a', 'b', 'c'])
    expect(prefs.density.value).toBe('default')
  })

  it('旧版本/未知列/重复项/全隐藏/非法密度均被规范化', () => {
    localStorage.setItem(
      storeKey,
      JSON.stringify({
        version: 0,
        order: ['c', 'c', 'ghost', 5],
        hidden: ['a', 'b', 'c', 'ghost'],
        density: 'huge',
      }),
    )

    const stored = readProTablePrefs('demo', columns)
    expect(stored.version).toBe(1)
    expect(stored.order).toEqual(['c', 'a', 'b']) // 去重 + 过滤未知 + 补全新列
    expect(stored.hidden).toEqual([]) // 全部隐藏视为脏数据
    expect(stored.density).toBe('default')

    const prefs = useProTablePrefs(ref(columns), 'demo')
    expect(prefs.visibleColumns.value.map((col) => col.prop)).toEqual(['c', 'a', 'b'])
  })

  it('至少保留一列可见, 并在重置后恢复默认顺序', () => {
    const prefs = useProTablePrefs(ref(columns), 'demo')
    prefs.toggleColumn('a')
    prefs.toggleColumn('b')
    prefs.toggleColumn('c') // 最后一列不可隐藏
    expect(prefs.visibleColumns.value.map((col) => col.prop)).toEqual(['c'])

    prefs.reset()
    expect(prefs.visibleColumns.value.map((col) => col.prop)).toEqual(['a', 'b', 'c'])
    expect(prefs.density.value).toBe('default')
    expect(localStorage.getItem(storeKey)).toBeNull()
  })
})
