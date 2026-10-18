<!-- Monaco 编辑器封装: v-model 内容/语言/主题/编码双向绑定, 页面经 defineAsyncComponent 异步加载避免进主包 -->
<template>
  <div ref="editorContainer" ></div>
</template>

<script setup lang="ts">
// 按需引入 Monaco: 编辑器核心 + CodeType 枚举 15 种语言的语法高亮,
// 语言服务 worker 仅保留 JSON(默认语言), 剔除 ts/css/html 三个重型 worker(合计约 8.7MB)
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api.js'
// 编辑器核心功能(查找/折叠/补全浮层等, 自带 UI 样式)
import 'monaco-editor/esm/vs/editor/editor.all.js'
// 语法高亮注册(与 CodeType 枚举一一对应)
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/java/java.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/cpp/cpp.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/html/html.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/css/css.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/sql/sql.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/dart/dart.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/ruby/ruby.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/csharp/csharp.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution.js'
import 'monaco-editor/esm/vs/basic-languages/xml/xml.contribution.js'
// JSON 语言服务(默认语言, 保留格式化与校验)
import 'monaco-editor/esm/vs/language/json/monaco.contribution.js'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'

// worker 分发: JSON 用专用 worker(校验/格式化), 其余语言用基础 worker(词法建议等)
;(self as unknown as { MonacoEnvironment?: monaco.Environment }).MonacoEnvironment = {
  getWorker: (_workerId: string, label: string): Worker =>
    label === 'json' ? new jsonWorker() : new editorWorker(),
}
// 定义组件属性
interface Props {
  modelValue?: string
  language?: string
  theme?: 'vs' | 'vs-dark' | 'hc-black'
  encoding?: string
  readOnly?: boolean
  fontSize?: number
  lineHeight?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  language: 'javascript',
  theme: 'vs',
  encoding: 'utf-8',
  readOnly: false,
  fontSize: 14,
  lineHeight: 1.5
})

// 定义事件
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [value: string]
}>()

// 编辑器实例和容器引用
const editorContainer = ref<HTMLElement | null>(null)
let monacoEditor: any = null

// 初始化编辑器
onMounted(async () => {
  if (editorContainer.value) {
    // const monaco = await import('monaco-editor')

    monacoEditor = monaco.editor.create(editorContainer.value, {
      value: props.modelValue,
      language: props.language,
      theme: props.theme,
      readOnly: props.readOnly,
      fontSize: props.fontSize,
      lineHeight: props.lineHeight,
      automaticLayout: true,
      minimap: { enabled: true },
      scrollBeyondLastLine: false,
      wordWrap: 'on'
    })

    // 监听编辑器内容变化
    monacoEditor.onDidChangeModelContent(() => {
      const value = monacoEditor.getValue()
      emit('update:modelValue', value)
      emit('change', value)
    })
  }
})

// 在组件卸载前销毁编辑器
onBeforeUnmount(() => {
  if (monacoEditor) {
    monacoEditor.dispose()
  }
})

// 监听属性变化
watch(() => props.modelValue, (newValue) => {
  if (monacoEditor && monacoEditor.getValue() !== newValue) {
    monacoEditor.setValue(newValue)
  }
})

watch(() => props.language, (newLanguage) => {
  if (monacoEditor) {
    const model = monacoEditor.getModel()
    if (model) {
      monaco.editor.setModelLanguage(model, newLanguage)
    }
  }
})

watch(() => props.theme, (newTheme) => {
  if (monacoEditor) {
    monaco.editor.setTheme(newTheme)
  }
})

// 创建TextDecoder
// const decoder = new TextDecoder("utf-8");


// 暴露方法给父组件
defineExpose({
  getInstance: () => monacoEditor,
  setValue: (value: string) => {
    if (monacoEditor) {
      monacoEditor.setValue(value)
    }
  },
  getValue: (): string => {
    return monacoEditor ? monacoEditor.getValue() : ''
  },
  updateOptions: (options: any) => {
    if (monacoEditor) {
      monacoEditor.updateOptions(options)
    }
  }
})
</script>
