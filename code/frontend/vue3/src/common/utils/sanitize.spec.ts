// sanitize 工具单测(REQ-010): 危险内容剔除契约
// 注: node 环境下 dompurify 会经 jsdom 回退构建 DOM, 因此消毒逻辑真实生效
import { describe, it, expect } from 'vitest'
import { sanitizeHtml } from './sanitize'

describe('sanitizeHtml', () => {
  it('剔除 script 标签与内联事件, 保留安全片段', () => {
    const out = sanitizeHtml('<script>alert(1)</script><p onclick="x()">hi</p>')
    expect(out).toContain('hi')
    expect(out).not.toContain('script')
    expect(out).not.toContain('onclick')
  })

  it('安全片段保持不变', () => {
    const clean = '<p>正常<b>加粗</b>内容</p>'
    expect(sanitizeHtml(clean)).toBe(clean)
  })
})
