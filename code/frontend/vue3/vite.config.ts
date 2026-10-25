import { fileURLToPath, URL } from 'node:url'
import { readFileSync, writeFileSync, mkdirSync, rmSync, existsSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
// 产物预压缩: 构建时同时生成 .gz/.br, 部署后由服务器直接回源压缩文件
import { compression } from 'vite-plugin-compression2'
// 开发插件
import VueRouter from 'unplugin-vue-router/vite'// 自动引入路由
import AutoImport from 'unplugin-auto-import/vite' //自动导入 API
import Components from 'unplugin-vue-components/vite'//自动导入组件
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers';
import { VueRouterAutoImports } from 'unplugin-vue-router'
import UnoCSS from 'unocss/vite'// css 辅助
import Icons from 'unplugin-icons/vite'//图标
import IconsResolver from 'unplugin-icons/resolver' //图标插件
// 文件在线预览(file-viewer): 自动发现已安装的 renderer preset 并复制 worker/wasm 离线资产
import { fileViewerRenderers, createFileViewerManualChunks } from '@file-viewer/vite-plugin'
// file-viewer 渲染器分包函数(与下方 manualChunks 组合)
const fvManualChunks = createFileViewerManualChunks()
// 代码根路径
import path from 'path'
const pathSrc = path.resolve(__dirname, 'src')
// 打包时从 package.json 读取版本号: 注入 __APP_VERSION__ 常量 + 构建产物 version.json
const pkgVersion = JSON.parse(readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8')).version as string
// 构建结束把版本写入产物根目录 version.json, 供线上前端轮询检测新版本
const versionFilePlugin = {
  name: 'write-version-file',
  apply: 'build' as const,
  closeBundle() {
    mkdirSync(resolve(__dirname, 'dist'), { recursive: true })
    writeFileSync(
      resolve(__dirname, 'dist', 'version.json'),
      JSON.stringify({ version: pkgVersion }),
    )
  },
}
// .ppt(97-2003 老格式)渲染链路清理: 其 wasm 引擎 + 16M CJK 字体包重 18M,
// 预览白名单已排除 .ppt(见 FilePreviewDialog), 构建后剔除该格式全部产物
// (源资产在 node_modules 完好, 恢复 .ppt 预览时移除本插件重新构建即可)
const pptLegacyPrunePlugin = {
  name: 'prune-ppt-legacy-assets',
  apply: 'build' as const,
  closeBundle() {
    const dist = resolve(__dirname, 'dist')
    // 老格式专用 vendor 目录(wasm 引擎 + 字体包)
    rmSync(resolve(dist, 'vendor', 'ppt'), { recursive: true, force: true })
    // 老格式专用 chunk 与字体/wasm 产物(含 .gz/.br 预压缩副本)
    if (!existsSync(resolve(dist, 'assets'))) return
    for (const name of readdirSync(resolve(dist, 'assets'))) {
      if (/^ppt-(font-cjk-.*\.otf|native-.*\.wasm|[\w-]+\.js)(\.(br|gz))?$/.test(name)) {
        rmSync(resolve(dist, 'assets', name), { force: true })
      }
    }
  },
}
// 代理
import { createProxy } from './tools/vite/proxy'; // 代理
import { killPort } from './tools/vite/kill_port';
// https://vite.dev/config/
export default defineConfig(
  ({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');
    // console.log('test_', env.VITE_PORT)
    killPort(env.VITE_PORT)

    const proxys = createProxy(JSON.parse(env.VITE_PROXY as string) as string[][])
    return {
      // 设置基础路径
      base: env.BASE_URL,

      // 打包时注入 package.json 版本号(运行时与 version.json 比对判断是否有新版本)
      define: {
        __APP_VERSION__: JSON.stringify(pkgVersion),
      },

      // 插件配置
      plugins: [
        versionFilePlugin,
        // 预压缩产物(gzip + brotli): 传输体积大幅下降, 不影响原始文件回退
        ...(mode === 'production'
          ? [compression({ algorithms: ['gzip', 'brotli'] })]
          : []),
        vue(),
        // 自动路由(特性/模块化架构):
        // 1. src/pages            —— 全局页面(首页/后台工作台/账户设置/404 等)
        // 2. src/modules/*/pages  —— 各业务模块页面, 按模块规范生成路由 /<模块名>/<页面>,
        //    如 src/modules/authorization/pages/user.vue -> /authorization/user
        //    页面与所在模块的 api/components/types 同目录, 删除模块文件夹即删除整个功能
        VueRouter({
          routesFolder: [
            'src/pages',
            {
              src: 'src/modules',
              // 匹配 pages 下任意层级页面(插件会追加 .vue 扩展名, 末段须为 *,
              // 否则 **.vue 无法跨目录, pages 子文件夹内的页面不会被注册)
              filePatterns: '**/pages/**/*',
              path: (file) => {
                // D:/.../src/modules/<模块>/pages/<页面>.vue -> <模块>/<页面>.vue
                const posixFile = file.replace(/\\/g, '/')
                const rest = posixFile.slice(posixFile.lastIndexOf('src/modules') + 'src/modules'.length + 1)
                return rest.replace('/pages/', '/')
              },
            },
          ],
          // 路由 meta 标记(登录拦截与侧边栏显示的依据):
          // 1. 首页与 404 为公开页, 不加标记
          // 2. 前台应用模块(rag 知识库问答 / agent 智能体编排)标记 app: 需登录, 但无侧边栏,
          //    从首页直接进入, 模块内孙页面导航由各模块页面自行承担
          // 3. 其余(后台工作台/账户设置/后台管理模块页面)标记 admin: 需登录 + 显示侧边栏,
          //    仅经头像下拉"后台管理"入口可达
          extendRoute: (route) => {
            const file = (route.component ?? '').replace(/\\/g, '/')
            const isPublic = file.endsWith('/src/pages/index.vue') || file.includes('/[..all].vue')
            // rag(AI 助手/知识库) 与 agent(智能体编排) 同属 AI 助手主应用: 无后台侧边栏,
            // 三者由 RagPageNav 内页导航同级切换
            const isMainApp = /\/src\/modules\/(rag|agent)\//.test(file)
            if (file && !isPublic) route.addToMeta(isMainApp ? { app: true } : { admin: true })
            // 独立页面(如账户设置): 属后台路由(需登录), 但页面自带导航, 不渲染侧边栏
            if (file.endsWith('/src/pages/setting.vue')) route.addToMeta({ standalone: true })
            // 版本信息页(系统介绍+版本时间线): 属后台路由(需登录), 页面自带布局, 不渲染侧边栏
            if (file.endsWith('/src/pages/version.vue')) route.addToMeta({ standalone: true })
          },
        }),
        // devtools 仅开发环境挂载, 生产构建零开销
        ...(mode === 'development' ? [vueDevTools()] : []),

        // 辅助导入和设定 tailwindcss 等 css 框架
        UnoCSS(),

        // Auto-import Element Plus APIs (ElMessage, ElNotification, etc.)
        AutoImport({
          // 自动导入 Vue 相关函数，如：ref, reactive, toRef 等
          imports: ['vue', VueRouterAutoImports, 'pinia'],
          // composition API 函数（例如 ElMessage, ElLoading
          resolvers: [ElementPlusResolver()

          ],
          dts: path.resolve(pathSrc, 'auto-imports.d.ts')
        }),

        // Auto-import Element Plus components from templates
        Components({
          // 自动注册全局公共组件(模板中无需 import):
          // src/common/components —— 与业务无关的通用组件(TableSearchBar/chat/ide/icons)
          // src/app/components    —— 应用壳组件(SysHeader/SysSidebar/SysFooter/设置面板)
          // 业务模块私有组件放在 src/modules/*/components, 使用时显式 import
          dirs: ['src/common/components', 'src/app/components'],
          resolvers: [
            // https://icones.netlify.app/ 自动注册图标组件“前缀-使用的图标库名称-图标名”  <i-ep-edit />
            IconsResolver({
              // prefix: 'Icon', // 修改前缀 默认 i
              enabledCollections: ['ep'] // 指定需要自动导入的图标库
            }),
            //自动导入 Element Plus 组件
            ElementPlusResolver(
              // 表示自动导入组件时，同步引入其对应的 CSS 样式文件。
              { importStyle: 'css' })
          ],
          dts: path.resolve(pathSrc, 'components.d.ts'), // 组件类型声明文件位置
          // 排除 MonacoEditor 组件(由页面 defineAsyncComponent 异步加载, 避免打进主包)
          exclude: [/BaseMonacoEdit\.vue$/],
        }),
        Icons({ autoInstall: true }), //自动下载图标库 必须在 Components 之后或独立存在
        // file-viewer 预览器: 显式限定渲染器(REQ-016 范围 = 图片/文本 + PDF/Word/Excel/PPT),
        // 排除 preset-office 附带的 hangul/iwork/wordperfect 等无关重型链路;
        // 构建时复制 worker/wasm 资产到 dist
        // inject: false —— 不把渲染器注册模块注入首屏入口(默认注入会让入口静态
        // 拉起全部 6 个渲染器 chunk, 约 2.3MB JS); 注册模块改由 FilePreviewDialog
        // 引入(见该文件), 渲染器随文件管理页懒加载, 首屏零开销
        fileViewerRenderers({
          autoPresets: false,
          renderers: ['image', 'text', 'pdf', 'word', 'spreadsheet', 'presentation'],
          formats: ['pdf', 'docx', 'docm', 'xlsx', 'xlsm', 'csv', 'pptx', 'pptm', 'ppsx',
            'txt', 'md', 'log', 'json', 'xml', 'yaml', 'yml', 'html',
            'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico', 'tiff', 'avif'],
          copyAssets: true,
          inject: false,
        }),

        // 构建后剔除 .ppt 老格式渲染链路产物(须在 copyAssets 之后执行)
        pptLegacyPrunePlugin,

      ],
      resolve: {
        alias: {
          '@': fileURLToPath(new URL('./src', import.meta.url))
        },
      },

      // 开发服务设置
      server: {
        port: Number(env.VITE_PORT),
        strictPort: true,
        host: '0.0.0.0',
        allowedHosts: true, // 允许所有 Host
        headers: {
          'Access-Control-Allow-Origin': '*'
        },
        // 代理
        proxy: proxys
      },

      // 构建产物预览服务(与开发服务同套代理, 便于绕开 dev 预构建直接验证 dist)
      preview: {
        proxy: proxys
      },

      // 生产构建: 体积/缓存优化
      build: {
        // 现代浏览器目标: 减少语法降级与 helper 体积
        target: 'es2020',
        // 现代浏览器原生支持 modulepreload, 省去 polyfill 注入
        modulePreload: { polyfill: false },
        cssCodeSplit: true,
        // 无需 gzip 体积统计, 加快构建
        reportCompressedSize: false,
        // 重型库已拆为独立 chunk(见下), 调高阈值避免无谓告警
        chunkSizeWarningLimit: 1200,
        rollupOptions: {
          output: {
            // 分包策略: 变更频率低的大库独立成块, 利于长效缓存;
            // 页面本身已由 unplugin-vue-router 懒加载, 此处只切第三方依赖
            // 注: rolldown 中 manualChunks 由 advancedChunks 仿真, 二者互斥
            // (同时给出时 manualChunks 整体被忽略), 故统一写在 advancedChunks.groups
            advancedChunks: {
              groups: [
                // 共享运行时助手(vite 预加载助手 / oxc transform helpers)单独成块:
                // 这类全图共用的小模块若不认领, 会被并入 file-viewer 渲染器分包,
                // 入口为取 2 个符号就得静态拉起数百 KB 渲染器代码。必须用 test
                // 认领 —— manualChunks 函数对虚拟模块(\0 前缀 id)的返回值不生效
                { name: 'runtime-helpers', priority: 10, test: /(?:vite\/preload-helper|@oxc-project)/ },
                // 其余按模块路径分组(与常见 manualChunks 写法等价)
                {
                  name(id: string) {
                    // file-viewer 按渲染器独立分包(worker/wasm 长效缓存, 不进主包)
                    const fvChunk = fvManualChunks(id)
                    if (fvChunk) return fvChunk
                    if (!id.includes('node_modules')) return
                    // Vue 全家桶(最高频, 单独缓存)
                    if (/[\\/]node_modules[\\/](@vue|vue|vue-router|pinia|vue-i18n|@vueuse)[\\/]/.test(id)) {
                      return 'vue-vendor'
                    }
                    if (id.includes('element-plus') || id.includes('@element-plus') || id.includes('dayjs')) {
                      return 'element-plus'
                    }
                    // ECharts 图表库(db 关系图用), 独立缓存
                    if (id.includes('echarts') || id.includes('zrender')) return 'echarts'
                    // Mermaid 及其图形依赖(聊天/导出时动态加载)
                    if (/[\\/]node_modules[\\/](mermaid|cytoscape|d3|d3-[^\\/]+|dagre[^\\/]*|elkjs|roughjs|khroma|@viz-js)[\\/]/.test(id)) {
                      return 'mermaid'
                    }
                    if (id.includes('monaco-editor')) return 'monaco'
                    if (id.includes('katex')) return 'katex'
                    if (id.includes('exceljs')) return 'exceljs'
                    if (id.includes('marked')) return 'markdown'
                    // Babylon.js 3D 引擎(独立 chunk 长效缓存)
                    if (id.includes('babylonjs') || id.includes('earcut')) return 'babylon'
                  },
                },
              ],
            },
          },
        },
      },

      // 依赖优化配置
      optimizeDeps: {
        // 显式包含常用依赖，避免运行时动态发现
        // include: [
        //   'element-plus/es',
        //   '@microsoft/fetch-event-source',
        // ]
        // 首次启动时强制预构建所有依赖（启动稍慢，但后续稳定）
        // force: true,
      }
    }
  })

