// httpError 单测: FastAPI detail 解析(字符串/422 数组)与 fetch 错误信息提取回退
import { describe, it, expect } from 'vitest'
import { parseFastApiDetail, extractHttpErrorMessage } from './httpError'

describe('parseFastApiDetail', () => {
  it('非对象/无 detail 字段返回 null', () => {
    expect(parseFastApiDetail(null)).toBeNull()
    expect(parseFastApiDetail(undefined)).toBeNull()
    expect(parseFastApiDetail('string')).toBeNull()
    expect(parseFastApiDetail(42)).toBeNull()
    expect(parseFastApiDetail({ message: 'x' })).toBeNull()
  })

  it('detail 为字符串时直接返回', () => {
    expect(parseFastApiDetail({ detail: '模板不存在' })).toBe('模板不存在')
  })

  it('detail 为 422 数组时拼接为 "字段: 消息" 并剔除 loc 中的 body 层级', () => {
    const detail = [{ loc: ['body', 'name'], msg: '字符串过长' }]
    expect(parseFastApiDetail({ detail })).toBe('name: 字符串过长')
  })

  it('多条校验错误以分号拼接, loc 多级路径以点连接', () => {
    const detail = [
      { loc: ['query', 'page'], msg: 'must be >= 1' },
      { loc: ['body', 'ids', 0], msg: 'ID 不能为空' },
    ]
    expect(parseFastApiDetail({ detail })).toBe('query.page: must be >= 1; ids.0: ID 不能为空')
  })

  it('无 loc 仅 msg 时直接使用 msg', () => {
    expect(parseFastApiDetail({ detail: [{ msg: '仅消息' }] })).toBe('仅消息')
  })

  it('空数组解析结果为 null(调用方回退默认文案)', () => {
    expect(parseFastApiDetail({ detail: [] })).toBeNull()
  })
})

describe('extractHttpErrorMessage', () => {
  it('JSON 响应携带 detail 字符串时返回 detail', async () => {
    const resp = new Response(JSON.stringify({ detail: '未授权' }), { status: 401 })
    expect(await extractHttpErrorMessage(resp)).toBe('未授权')
  })

  it('JSON 响应携带 422 数组时返回拼接信息', async () => {
    const resp = new Response(
      JSON.stringify({ detail: [{ loc: ['body', 'value'], msg: '非法数值' }] }),
      { status: 422 },
    )
    expect(await extractHttpErrorMessage(resp)).toBe('value: 非法数值')
  })

  it('非 JSON 响应回退为 "HTTP 状态码" 文案', async () => {
    const resp = new Response('<html>gateway error</html>', { status: 502 })
    expect(await extractHttpErrorMessage(resp)).toBe('HTTP 502')
  })

  it('JSON 但无可解析 detail 时回退状态码文案', async () => {
    const resp = new Response(JSON.stringify({ foo: 1 }), { status: 500 })
    expect(await extractHttpErrorMessage(resp)).toBe('HTTP 500')
  })
})
