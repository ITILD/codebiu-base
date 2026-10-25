// 模型配置类型单测: 生图(image)类型的选项映射与后端能力清单对齐
import { describe, expect, it } from 'vitest'
import {
  ModelServerType,
  ModelType,
  capabilityOptionsFor,
  modelTypeLabel,
  modelTypeOptions,
  serverTypeOptionsFor,
  testedCapabilities,
  type ModelConfig,
} from './model_config'

describe('image 模型类型映射', () => {
  it('模型类型选项包含生图', () => {
    expect(modelTypeOptions.some(o => o.value === ModelType.IMAGE)).toBe(true)
    expect(modelTypeLabel(ModelType.IMAGE)).toBe('生图')
  })

  it('服务方案仅开放 OpenAI 兼容与 DashScope 兼容模式', () => {
    const values = serverTypeOptionsFor(ModelType.IMAGE).map(o => o.value)
    expect(values).toEqual([ModelServerType.OPENAI, ModelServerType.DASHSCOPE])
  })

  it('能力项与后端 MODEL_CAPABILITIES 对齐(文生图/图生图)', () => {
    expect(capabilityOptionsFor[ModelType.IMAGE]).toEqual([
      { key: 'image', label: '文生图' },
      { key: 'image_edit', label: '图生图' },
    ])
  })

  it('未测试时能力标签为空, 已测试则按 check_result 渲染', () => {
    expect(testedCapabilities(null)).toEqual([])
    const config = {
      model_type: ModelType.IMAGE,
      check_result: {
        image: { capability: 'image', label: '', ok: true, detail: '生成 1 张' },
        image_edit: { capability: 'image_edit', label: '', ok: false, error: '超时' },
      },
    } as unknown as ModelConfig
    expect(testedCapabilities(config)).toEqual([
      { key: 'image', label: '文生图', ok: true, detail: '生成 1 张', error: '' },
      { key: 'image_edit', label: '图生图', ok: false, detail: '', error: '超时' },
    ])
  })
})
