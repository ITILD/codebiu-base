import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults, type ViteUserConfig } from 'vitest/config'
import viteConfig from './vite.config'

// vite.config 导出为工厂函数(按 mode 分支), 须先解析成普通对象再合并:
// mergeConfig 不接受回调形式, 直接传函数会报 "Cannot merge config in form of callback"
const resolvedViteConfig: ViteUserConfig =
  typeof viteConfig === 'function'
    ? // 以 development 模式解析(读取 .env.development 的代理等变量;
      // 'test' 模式下 loadEnv 读不到 VITE_PROXY 会 JSON.parse(undefined) 崩溃)
      ((await viteConfig({ mode: 'development', command: 'serve' })) as ViteUserConfig)
    : (viteConfig as ViteUserConfig)

export default mergeConfig(
  // vite 配置需转换为 vitest 的用户配置类型
  resolvedViteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
