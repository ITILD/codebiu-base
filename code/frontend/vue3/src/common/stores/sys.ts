/**
 * 全局系统设置状态:主题(明暗)、布局(侧边栏/头部开关)、响应式断点、语言等。
 * 主题偏好持久化在 localStorage(sys-theme), 登录后再与后端用户配置同步。
 */
import { useDark, useBreakpoints, useLocalStorage } from '@vueuse/core'
import type { ThemeMode } from '@/common/types/theme'

// 主题偏好缓存键: index.html 首屏启动画面在 Vue 挂载前读取同一键, 保证等待画面与用户设置一致
export const THEME_STORAGE_KEY = 'sys-theme'
// useDark 自身持久化键(历史数据兼容读取)
const VUEUSE_THEME_KEY = 'vueuse-color-scheme'

const isThemeMode = (value: string | null): value is ThemeMode =>
  value === 'light' || value === 'dark' || value === 'auto'

/** 读取本地主题偏好(优先用户设置, 其次 useDark 历史值, 最后跟随系统) */
const readThemeMode = (): ThemeMode => {
  const saved = localStorage.getItem(THEME_STORAGE_KEY)
  if (isThemeMode(saved)) return saved
  const vueuseSaved = localStorage.getItem(VUEUSE_THEME_KEY)
  return isThemeMode(vueuseSaved) ? vueuseSaved : 'auto'
}

const SysSettingStore = defineStore('sysSetting', () => {
  // 项目断点(与 UnoCSS presetWind3 的 md/lg 前缀对齐):
  // 手机 <768 / 平板 768-1023 / 桌面 >=1024
  const breakpoints = useBreakpoints({ md: 768, lg: 1024 })
  const baseMd = 768
  const sysStyle = ref({
    headFootShow: true,
    isUserControlShow: false,
    // 左侧选择栏
    leftControlShow: true,
    // 移动端侧边栏抽屉开关
    isSidebarDrawerOpen: false,
    // 平板及以上(>=768, 与 CSS md: 类的 min-width:768px 对齐): 控制侧边栏显隐/汉堡按钮
    isMd: breakpoints.greater('md'),
    // 桌面及以上(>=1024): 控制侧边栏默认展开(平板默认折叠)
    isLg: breakpoints.greater('lg'),
    theme: {
      isDark: useDark(),
      // 用户主题偏好: auto light dark
      themeValue: readThemeMode(),
      head: [{ height: '35px' }],
      leftControl: {
        tabPosition: 'left'
      }
    },
    // 语言切换统一由 common/i18n/language.ts 管理(持久化于 localStorage)
  })

  const sysObj = {
    $ObjLargeTemp: new Map()
  }
  // isMd/isLg 由 useBreakpoints 响应式监听窗口变化驱动(替代原 window.onresize 全局赋值)
  // 设置弹窗显隐
  const isSysSettingShow = ref(false)
  // 根据主题值更改 isDark(light/dark/auto 三态切换), 并持久化到本地供首屏与下次启动使用
  const changeIsDarkByThemeValue = () => {
    const themeValue = sysStyle.value.theme.themeValue
    switch (themeValue) {
      case 'light':
        sysStyle.value.theme.isDark = false
        break
      case 'dark':
        sysStyle.value.theme.isDark = true
        break
      default:
        // auto: 媒体查询检测夜晚/黑暗模式
        sysStyle.value.theme.isDark =
          window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        break
    }
    localStorage.setItem(THEME_STORAGE_KEY, themeValue)
    return sysStyle.value.theme.isDark
  }
  /**
   * 套用主题模式(本地状态 + localStorage + html.dark 类同步)
   * 登录成功后据此切换为该用户保存的样式配置
   */
  const applyThemeValue = (value: ThemeMode) => {
    sysStyle.value.theme.themeValue = value
    changeIsDarkByThemeValue()
  }

  // 悬浮工具(全屏/截图/隐藏)显隐: 隐藏后可在 设置-外观 中重新开启
  const floatToolsHidden = useLocalStorage('sys-float-tools-hidden', false)

  // store 创建时按本地偏好立即套用, 与 index.html 首屏脚本保持一致
  changeIsDarkByThemeValue()

  return { sysStyle, sysObj, isSysSettingShow, floatToolsHidden, changeIsDarkByThemeValue, applyThemeValue }
})

export { SysSettingStore }
