import { createI18n } from 'vue-i18n'
import { protableKeys } from './keys/protable'
import { codegenKeys } from './keys/codegen'
import { i18nAdminKeys } from './keys/i18nAdmin'
import { layoutKeys } from './keys/layout'
import { assistantKeys } from './keys/assistant'

/**
 * 系统语言切换(中/英/日三语)
 * - 词条用「三元数组」按语言下标对齐, 生成各语言消息包(便于集中维护对照)
 * - 语言选择持久化于 localStorage(sys-language), 首次访问按浏览器语言自动匹配
 * - Element Plus 组件内建文案(pagination/date-picker 等)由 App.vue 依据
 *   currentLanguage 提供 EP 语言包, 与界面语言同步切换
 */

// 支持的语言码(下标与 languageTypeFullArray / 各词条翻译数组严格对齐)
const languageTypeArray = ['zh', 'ja', 'en'] as const
// 语言全称(用于语言选择器展示, 以各自语言书写)
const languageTypeFullArray = ['简体中文', '日本語', 'English']

// 语言持久化键
const LANG_KEY = 'sys-language'

// 语言对照表: key → [zh, ja, en]
const languageObj = {
  // 通用
  language: ['语言选择', '言語選択', 'Language'],
  theme: ['主题', 'テーマ', 'Theme'],
  dark: ['暗', 'ダーク', 'Dark'],
  light: ['明', 'ライト', 'Light'],
  autoSys: ['跟随系统', 'システムに従う', 'Follow System'],
  auto: ['自动', '自動', 'Auto'],
  home: ['首页', 'ホーム', 'Home'],
  about: ['关于', 'アバウト', 'About'],
  titleDemo: ['标题', 'タイトル', 'Title'],
  username: ['用户名', 'ユーザー名', 'Username'],
  email: ['邮箱', 'メール', 'Email'],
  sign_in: ['登录', 'ログイン', 'Sign In'],
  sign_up: ['注册', '登録する', 'Sign Up'],
  back_to_login: ['返回登录', 'ログインに戻る', 'Back to Login'],
  search: ['搜索', 'サーチ', 'Search'],
  // 首页
  g_night: ['夜深了', '夜も更けて', 'Up Late'],
  g_morning: ['早上好', 'おはようございます', 'Good Morning'],
  g_noon: ['中午好', 'こんにちは', 'Midday'],
  g_afternoon: ['下午好', 'こんにちは', 'Good Afternoon'],
  g_evening: ['晚上好', 'こんばんは', 'Good Evening'],
  // 问候格式: {g}=时段问候, {name}=昵称
  hello_fmt: ['{g}，{name}', '{g}、{name}', '{g}, {name}'],
  home_sub: ['像打理花园一样，安放你的数据与灵感。', '庭を手入れるように、データとインスピレーションを。', 'Tend your data and inspiration like a garden.'],
  home_login_hint: ['登录后可用个人小站、知识库等应用。', 'ログインすると各種アプリを利用できます。', 'Sign in to access all apps.'],
  home_recent: ['最近访问', '最近のアクセス', 'Recent'],
  home_apps: ['应用', 'アプリ', 'Apps'],
  home_app_desc: ['进入应用开始使用。', 'アプリを開いて利用を開始。', 'Open the app to get started.'],
  // 登录/注册
  label_password: ['密码', 'パスワード', 'Password'],
  label_confirm_password: ['确认密码', 'パスワード(確認)', 'Confirm Password'],
  label_email_code: ['邮箱验证码', 'メール確認コード', 'Email Code'],
  placeholder_username: ['请输入用户名…', 'ユーザー名を入力…', 'Enter username…'],
  placeholder_password: ['请输入密码…', 'パスワードを入力…', 'Enter password…'],
  placeholder_password_again: ['请再次输入密码…', 'もう一度パスワードを入力…', 'Enter password again…'],
  placeholder_email_code: ['请输入邮箱验证码…', '確認コードを入力…', 'Enter email code…'],
  remember_me: ['记住我', 'ログイン状態を保持', 'Remember Me'],
  send_code: ['发送验证码', '確認コードを送信', 'Send Code'],
  resend_in: ['{n}s 后重发', '{n}秒後に再送信', 'Resend in {n}s'],
  login_failed: ['登录失败，请检查用户名和密码', 'ログインに失敗しました。ユーザー名とパスワードをご確認ください', 'Login failed. Check your username and password'],
  rule_username_required: ['请输入用户名', 'ユーザー名を入力してください', 'Username is required'],
  rule_password_required: ['请输入密码', 'パスワードを入力してください', 'Password is required'],
  rule_password_min: ['密码至少6位', 'パスワードは6文字以上', 'At least 6 characters'],
  rule_username_len: ['用户名需 3-20 个字符', 'ユーザー名は3〜20文字', 'Must be 3-20 characters'],
  rule_email_required: ['请输入邮箱地址', 'メールアドレスを入力してください', 'Email is required'],
  rule_email_invalid: ['请输入正确的邮箱地址', '有効なメールアドレスを入力してください', 'Enter a valid email address'],
  rule_code_required: ['请输入邮箱验证码', '確認コードを入力してください', 'Email code is required'],
  rule_confirm_required: ['请确认密码', '確認用パスワードを入力してください', 'Please confirm password'],
  rule_password_mismatch: ['两次输入的密码不一致', 'パスワードが一致しません', 'Passwords do not match'],
  msg_code_sent: ['验证码已发送，请查收邮箱', '確認コードを送信しました。メールをご確認ください', 'Code sent. Check your email'],
  msg_code_send_failed: ['验证码发送失败', '確認コードの送信に失敗しました', 'Failed to send code'],
  msg_register_failed: ['注册失败，请检查输入信息', '登録に失敗しました。入力内容をご確認ください', 'Sign up failed. Check your input'],
  // 后台管理
  admin: ['后台管理', '管理画面', 'Admin'],
  admin_welcome: ['高效有序的管理工作台。', '効率的で整然とした管理ワークベンチ。', 'An organized admin workbench.'],
  admin_refresh: ['刷新数据', 'データ更新', 'Refresh'],
  admin_shortcuts: ['快捷入口', 'クイックアクセス', 'Shortcuts'],
  admin_sysinfo: ['系统信息', 'システム情報', 'System Info'],
  admin_no_recent: ['暂无访问记录', 'アクセス記録はまだありません', 'No history yet'],
  admin_cpu: ['CPU 使用率', 'CPU使用率', 'CPU Usage'],
  admin_memory: ['内存使用率', 'メモリ使用率', 'Memory Usage'],
  admin_disk: ['磁盘使用率', 'ディスク使用率', 'Disk Usage'],
  admin_network: ['网络连通', 'ネットワーク接続', 'Network'],
  admin_net_sub: ['外网探测成功数 / 总数', '外部プローブ成功数 / 総数', 'Probes OK / total'],
  admin_no_data: ['暂无数据', 'データなし', 'No data'],
  admin_cores_threads: ['{c} 核 / {t} 线程', '{c}コア / {t}スレッド', '{c} cores / {t} threads'],
  admin_sysver: ['系统版本', 'システムバージョン', 'System Version'],
  admin_env: ['运行环境', '実行環境', 'Environment'],
  admin_theme_mode: ['主题模式', 'テーマモード', 'Theme Mode'],
  admin_screen: ['屏幕档位', '画面段階', 'Screen Tier'],
  env_dev: ['开发环境', '開発環境', 'Development'],
  env_prod: ['生产环境', '本番環境', 'Production'],
  screen_desktop: ['桌面(≥1024)', 'デスクトップ(≥1024)', 'Desktop (≥1024)'],
  screen_tablet: ['平板(768-1023)', 'タブレット(768-1023)', 'Tablet (768–1023)'],
  screen_phone: ['手机(<768)', 'モバイル(<768)', 'Mobile (<768)'],
  // 账户设置
  tab_profile: ['基本信息', '基本情報', 'Profile'],
  tab_password: ['修改密码', 'パスワード変更', 'Password'],
  tab_model: ['模型设置', 'モデル設定', 'Models'],
  tab_appearance: ['外观设置', '外観設定', 'Appearance'],
  tab_permission: ['我的权限', '自分の権限', 'Permissions'],
  float_tools: ['悬浮工具', 'フロートツール', 'Float Tools'],
} as Record<string, string[]>

// 合并各功能模块的词条(每个模块独立文件维护, 避免多人/多任务改同一文件冲突)
Object.assign(languageObj, protableKeys, codegenKeys, i18nAdminKeys, layoutKeys, assistantKeys)

/** 首次访问按浏览器语言自动匹配; 已有用户选择时以 localStorage 为准 */
function detectLanguage(): string {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved && (languageTypeArray as readonly string[]).includes(saved)) return saved
  } catch { /* 隐私模式等场景忽略 */ }
  const nav = (navigator.language || 'zh').toLowerCase()
  if (nav.startsWith('zh')) return 'zh'
  if (nav.startsWith('ja')) return 'ja'
  if (nav.startsWith('en')) return 'en'
  return 'zh'
}

const initial = detectLanguage()

// 语言对照选择格式(语言选择器选项: value=语言码, label=该语言全称)
const languageOptions = languageTypeArray.map((value, index) => ({
  value,
  label: languageTypeFullArray[index],
}))

const i18n = createI18n({
  legacy: false,
  locale: initial,
  fallbackLocale: 'zh',
  messages: {},
})

// 生成各语言消息包
for (let index = 0; index < languageTypeArray.length; index++) {
  const languageType = languageTypeArray[index]
  const thisLanguageTypeObj = {} as Record<string, string>
  for (const key in languageObj) {
    thisLanguageTypeObj[key] = languageObj[key][index]
  }
  i18n.global.setLocaleMessage(languageType, thisLanguageTypeObj)
}

/**
 * 当前语言(响应式): 供顶栏切换器/EP ConfigProvider 等订阅展示
 * 注意: legacy:false 下 i18n.global.locale 是 Ref, 读写须走 .value
 */
const currentLanguage = ref(initial)

/** 切换语言: 更新 i18n + html lang(读屏/字体渲染) + localStorage 持久化 */
function changeLanguage(lang: string) {
  if (!(languageTypeArray as readonly string[]).includes(lang)) return
  i18n.global.locale.value = lang
  currentLanguage.value = lang
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : lang
  try {
    localStorage.setItem(LANG_KEY, lang)
  } catch { /* 忽略写入失败(隐私模式) */ }
}

// 启动时同步 html lang 到初始语言
changeLanguage(initial)

/**
 * 应用后台维护的词条覆盖(运行时热更新, 无需重新构建前端)
 * @param overrides 覆盖词条: key → [zh, ja, en]; 空字符串表示该语言不覆盖
 */
function applyI18nOverrides(overrides: Record<string, string[]>) {
  for (let index = 0; index < languageTypeArray.length; index++) {
    const languageType = languageTypeArray[index]
    const patch: Record<string, string> = {}
    for (const key in overrides) {
      const value = overrides[key]?.[index]
      if (typeof value === 'string' && value.trim()) patch[key] = value
    }
    if (Object.keys(patch).length) i18n.global.mergeLocaleMessage(languageType, patch)
  }
}

export {
  i18n,
  languageObj,
  languageOptions,
  currentLanguage,
  changeLanguage,
  applyI18nOverrides,
  languageTypeFullArray,
}
