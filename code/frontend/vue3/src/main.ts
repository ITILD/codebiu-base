import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate';
import App from './App.vue'
import router from './router'
/*
「reset 必须最先加载」同等特异性下源顺序会决定胜负，行为不可预测
*/
import '@unocss/reset/tailwind.css'// 重置边距 margin等0
// Element Plus 命令式服务样式(ElMessage/ElMessageBox/ElNotification/ElLoading
// 不经模板渲染, resolver 无法按需注入, 手动补齐; 其余组件样式由 resolver 按需引入)
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/theme-chalk/dark/css-vars.css' // 暗色模式 CSS 变量(体积小, 随主题常驻)
// 自定义主题(含 :root / html.dark 变量与组件微调)必须在 element-plus 样式之后加载,
// 否则同特异性下 element 的默认变量(灰底/蓝色主色)会覆盖掉墨绿自然笔记主题
import './assets/main.css'
import 'virtual:uno.css'
import { i18n } from '@/common/i18n/language'
import { ellipsisDirective } from '@/common/directives/ellipsis'
const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
pinia.use(piniaPluginPersistedstate)
app.use(router)
app.use(i18n)
// 全局指令: 文字溢出时才挂原生 title(hover 显示全文), 详见 directives/ellipsis.ts
app.directive('ellipsis', ellipsisDirective)

// 全局异常兜底: 组件内异常由 AppErrorBoundary 展示; 这里只做统一记录,
// 便于排查事件回调/异步链路中未被捕获的错误(避免控制台噪音掩盖真实问题)
app.config.errorHandler = (err, _instance, info) => {
  console.error('[app error]', info, err)
}
window.addEventListener('unhandledrejection', (event) => {
  console.error('[unhandled rejection]', event.reason)
})

app.mount('#app')
