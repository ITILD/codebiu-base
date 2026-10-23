// datetime 工具单测(REQ-010): 三种格式化与空值/非法值契约
import { describe, it, expect } from 'vitest'
import { formatDate, formatDateTime, formatTimeShort } from './datetime'

describe('datetime 格式化', () => {
  // 本地时区无关的安全时间点(正午)
  const iso = new Date(2024, 2, 5, 10, 20, 30).toISOString()

  it('formatDate: 输出含年/月/日', () => {
    const out = formatDate(iso)
    expect(out).toContain('2024')
    expect(out).toContain('03')
    expect(out).toContain('05')
  })

  it('formatDateTime: 输出日期与时间(时分)', () => {
    const out = formatDateTime(iso)
    expect(out).toContain('2024')
    expect(out).toMatch(/\d{2}:\d{2}/)
  })

  it('formatTimeShort: 短时间含月日与时分', () => {
    const out = formatTimeShort(iso)
    expect(out).toContain('03')
    expect(out).toMatch(/\d{2}:\d{2}/)
  })

  it('空值/非法值统一返回空串', () => {
    for (const fn of [formatDate, formatDateTime, formatTimeShort]) {
      expect(fn(null)).toBe('')
      expect(fn(undefined)).toBe('')
      expect(fn('not-a-date')).toBe('')
      expect(fn('')).toBe('')
    }
  })
})
