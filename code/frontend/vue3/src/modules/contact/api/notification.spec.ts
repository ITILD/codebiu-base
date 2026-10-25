// SSE 帧增量解析单测: 完整帧 / 跨 chunk 半帧 / CRLF / 注释与多行 data
import { describe, expect, it } from 'vitest'
import { parseSseBuffer } from './notification'

describe('parseSseBuffer', () => {
  it('解析完整帧并返回空残留', () => {
    const { frames, rest } = parseSseBuffer('', 'event: unread\ndata: {"count":3}\n\n')
    expect(frames).toEqual([{ event: 'unread', data: '{"count":3}' }])
    expect(rest).toBe('')
  })

  it('支持跨 chunk 半帧', () => {
    const first = parseSseBuffer('', 'event: notif')
    expect(first.frames).toEqual([])
    expect(first.rest).toBe('event: notif')

    const second = parseSseBuffer(first.rest, 'ication\ndata: {"id":1}\n\n')
    expect(second.frames).toEqual([{ event: 'notification', data: '{"id":1}' }])
    expect(second.rest).toBe('')
  })

  it('兼容 CRLF、注释行与多行 data', () => {
    const chunk = [
      ': keep-alive',
      'event: ping',
      'data: {}',
      '',
      'event: unread',
      'data: 1',
      'data: 2',
      '',
      '',
    ].join('\r\n')
    const { frames, rest } = parseSseBuffer('', chunk)
    expect(frames).toEqual([
      { event: 'ping', data: '{}' },
      { event: 'unread', data: '1\n2' },
    ])
    expect(rest).toBe('')
  })

  it('无 data 的帧被丢弃, 未声明 event 默认 message', () => {
    const { frames } = parseSseBuffer('', 'event: ping\n\ndata: hello\n\n')
    expect(frames).toEqual([{ event: 'message', data: 'hello' }])
  })
})
