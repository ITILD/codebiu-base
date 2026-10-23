// localstorage 工具单测: 序列化往返/异常回退/键枚举/容量统计(jsdom 提供 localStorage)
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  getLocalStorageKeys,
  setLocalStorageItem,
  getLocalStorageItem,
  removeLocalStorageItem,
  clearLocalStorage,
  isLocalStorageAvailable,
  getLocalStorageSizeInfo,
} from './localstorage'

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('set/get 往返', () => {
  it('对象/数组/数字/布尔/字符串 均按 JSON 序列化往返', () => {
    setLocalStorageItem('obj', { a: 1, b: 'x' })
    setLocalStorageItem('arr', [1, 2, 3])
    setLocalStorageItem('num', 42)
    setLocalStorageItem('bool', false)
    setLocalStorageItem('str', 'hello')
    expect(getLocalStorageItem<{ a: number; b: string }>('obj')).toEqual({ a: 1, b: 'x' })
    expect(getLocalStorageItem<number[]>('arr')).toEqual([1, 2, 3])
    expect(getLocalStorageItem<number>('num')).toBe(42)
    expect(getLocalStorageItem<boolean>('bool')).toBe(false)
    expect(getLocalStorageItem<string>('str')).toBe('hello')
  })

  it('不存在的键返回 null', () => {
    expect(getLocalStorageItem('missing')).toBeNull()
  })

  it('值为非法 JSON 时返回 null 且不抛错', () => {
    localStorage.setItem('broken', '{not valid json')
    expect(getLocalStorageItem('broken')).toBeNull()
    expect(console.error).toHaveBeenCalled()
  })
})

describe('remove/clear', () => {
  it('remove 后键不存在且返回 true', () => {
    setLocalStorageItem('k', 1)
    expect(removeLocalStorageItem('k')).toBe(true)
    expect(getLocalStorageItem('k')).toBeNull()
    // 移除不存在的键同样成功(幂等)
    expect(removeLocalStorageItem('k')).toBe(true)
  })

  it('clear 清空全部键且返回 true', () => {
    setLocalStorageItem('a', 1)
    setLocalStorageItem('b', 2)
    expect(clearLocalStorage()).toBe(true)
    expect(getLocalStorageKeys()).toEqual([])
  })
})

describe('getLocalStorageKeys', () => {
  it('返回按字母排序的全部键', () => {
    setLocalStorageItem('zebra', 1)
    setLocalStorageItem('apple', 2)
    setLocalStorageItem('mango', 3)
    expect(getLocalStorageKeys()).toEqual(['apple', 'mango', 'zebra'])
  })
})

describe('isLocalStorageAvailable', () => {
  it('jsdom 环境下可用', () => {
    expect(isLocalStorageAvailable()).toBe(true)
    // 探测键不应残留
    expect(localStorage.getItem('__storage_test__')).toBeNull()
  })
})

describe('getLocalStorageSizeInfo', () => {
  it('totalSize 按 key+value 字符长度累计, usagePercent 封顶 100', () => {
    setLocalStorageItem('ab', 12345) // value 序列化为 "12345"(5 字符) + key 2 = 7
    const info = getLocalStorageSizeInfo()
    expect(info.keyCount).toBe(1)
    expect(info.totalSize).toBe(7)
    expect(info.usagePercent).toBeGreaterThan(0)
    expect(info.usagePercent).toBeLessThanOrEqual(100)
  })
})
