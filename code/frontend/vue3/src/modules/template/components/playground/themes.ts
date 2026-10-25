/**
 * 组件选型主题注册表
 * 每个主题通过一组 CSS 变量覆盖 Element Plus 皮肤(主色/圆角/字体/背景/边框),
 * 由 ThemeShowcase 在根容器注入, 整页组件自动换肤; 新增主题只需在此追加一项。
 *
 * 视觉原则: 四套主题共享"纸感 + 低饱和 + 柔边光晕"的底子, 只在色相/字体/圆角上分化,
 * 避免出现大面积纯色(纯蓝/纯黑)与原生素描边, 保证与全站淡雅笔记风同源。
 */
import type { CSSProperties } from 'vue'

/** 主题定义 */
export interface PlaygroundTheme {
  /** 主题唯一键 */
  key: string
  /** 主题名(导航/卡片标题) */
  name: string
  /** 主题描述 */
  desc: string
  /** 主题页路由路径 */
  path: string
  /** 主题根容器注入的 CSS 变量(覆盖 Element Plus) */
  vars: Record<string, string>
  /** 主题根容器附加类(底色/文字/装饰) */
  rootClass: string
  /** 主题横幅附加类 */
  bannerClass: string
  /** 卡片预览色板(主题选择卡上的色块) */
  colors: string[]
  /** 氛围纸纹层(淡墨晕染/纸纤维/网格), 渲染在内容之下的绝对定位层 */
  atmosphere?: CSSProperties
  /** 横幅右上角的闲章单字(朱砂小印, 可选) */
  seal?: string
}

/** 商务风: 黛青主色 + 小圆角 + 暖灰纸面, 正式克制但不冰冷 */
const business: PlaygroundTheme = {
  key: 'business',
  name: '商务风',
  desc: '黛青主色、小圆角、暖灰纸面，正式克制的办公风格。',
  path: '/template/playground/business',
  vars: {
    // 主色(黛青, 低饱和墨蓝)及明暗梯度
    '--el-color-primary': '#3d5a6c',
    '--el-color-primary-dark-2': '#324b5b',
    '--el-color-primary-light-3': '#778c98',
    '--el-color-primary-light-5': '#9eacb5',
    '--el-color-primary-light-7': '#c5cdd3',
    '--el-color-primary-light-8': '#d8dee2',
    '--el-color-primary-light-9': '#ebeeef',
    // 功能色梯度(竹青 / 赭石 / 陶红 / 石墨)
    '--el-color-success': '#3f7a55',
    '--el-color-success-dark-2': '#356648',
    '--el-color-success-light-3': '#79a288',
    '--el-color-success-light-5': '#9fbcaa',
    '--el-color-success-light-7': '#c7d6cc',
    '--el-color-success-light-8': '#d8e3db',
    '--el-color-success-light-9': '#ebf1ed',
    '--el-color-warning': '#a8762e',
    '--el-color-warning-dark-2': '#8d6327',
    '--el-color-warning-light-3': '#c29f6d',
    '--el-color-warning-light-5': '#d4bb97',
    '--el-color-warning-light-7': '#e5d6c0',
    '--el-color-warning-light-8': '#eee3d3',
    '--el-color-warning-light-9': '#f6f0e7',
    '--el-color-danger': '#a84b42',
    '--el-color-danger-dark-2': '#8c3e37',
    '--el-color-danger-light-3': '#c2817b',
    '--el-color-danger-light-5': '#d4a5a1',
    '--el-color-danger-light-7': '#e5c9c6',
    '--el-color-danger-light-8': '#eedbd9',
    '--el-color-danger-light-9': '#f6ebea',
    '--el-color-info': '#5b6670',
    '--el-color-info-dark-2': '#4b545d',
    '--el-color-info-light-3': '#8c949b',
    '--el-color-info-light-5': '#adb3b8',
    '--el-color-info-light-7': '#ced2d5',
    '--el-color-info-light-8': '#dee1e3',
    '--el-color-info-light-9': '#eef0f1',
    // 文字 / 背景 / 边框 / 填充(暖纸调, 不做纯白冷灰)
    '--el-text-color-primary': '#2b333a',
    '--el-text-color-regular': '#46525c',
    '--el-text-color-secondary': '#6b7681',
    '--el-bg-color': '#ffffff',
    '--el-bg-color-overlay': '#ffffff',
    '--el-bg-color-page': '#f4f3ef',
    '--el-border-color': '#d8d5cd',
    '--el-border-color-light': '#e4e1da',
    '--el-border-color-lighter': '#eeebe4',
    '--el-border-color-extra-light': '#f5f3ed',
    '--el-fill-color': '#efede7',
    '--el-fill-color-dark': '#e8e5dd',
    '--el-fill-color-light': '#f4f2ed',
    '--el-fill-color-lighter': '#f8f7f3',
    '--el-fill-color-blank': '#ffffff',
    // 圆角 / 字体 / 开关激活色
    '--el-border-radius-base': '4px',
    '--el-border-radius-small': '3px',
    '--el-font-family': "'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    '--el-switch-on-color': '#3d5a6c',
  },
  rootClass: 'bg-[#f4f3ef] text-[#2b333a] border border-[#d8d5cd]',
  bannerClass: 'bg-[#3d5a6c] text-[#f2f6f7] border border-[#324b5b]',
  colors: ['#3d5a6c', '#ffffff', '#f4f3ef', '#2b333a'],
  seal: '商',
  atmosphere: {
    // 冷调纸面: 左上淡墨晕 + 极细方格(办公纸的秩序感)
    backgroundImage:
      'radial-gradient(64% 48% at 4% 0%, rgba(61, 90, 108, 0.12) 0%, transparent 62%),'
      + 'radial-gradient(52% 38% at 100% 6%, rgba(61, 90, 108, 0.07) 0%, transparent 66%),'
      + 'repeating-linear-gradient(0deg, rgba(61, 90, 108, 0.05) 0 1px, transparent 1px 32px),'
      + 'repeating-linear-gradient(90deg, rgba(61, 90, 108, 0.05) 0 1px, transparent 1px 32px)',
  },
}

/** 哈利波特: 羊皮纸底 + 鎏金主色 + 衬线字体, 魔法复古风 */
const harryPotter: PlaygroundTheme = {
  key: 'harry_potter',
  name: '哈利波特',
  desc: '羊皮纸底、鎏金主色、衬线字体，魔法世界的复古风格。',
  path: '/template/playground/harry_potter',
  vars: {
    // 主色(鎏金)及明暗梯度
    '--el-color-primary': '#a5803a',
    '--el-color-primary-dark-2': '#84662e',
    '--el-color-primary-light-3': '#c0a675',
    '--el-color-primary-light-5': '#d2c09d',
    '--el-color-primary-light-7': '#e4d9c4',
    '--el-color-primary-light-8': '#ede5d7',
    '--el-color-primary-light-9': '#f6f0e8',
    // 功能色梯度(格林芬多红 / 斯莱特林绿)
    '--el-color-success': '#2d5a3d',
    '--el-color-success-dark-2': '#244831',
    '--el-color-success-light-3': '#5b8069',
    '--el-color-success-light-5': '#8aa694',
    '--el-color-success-light-7': '#b8ccbf',
    '--el-color-success-light-8': '#cfe0d5',
    '--el-color-success-light-9': '#e7f0ea',
    '--el-color-warning': '#a0621a',
    '--el-color-warning-dark-2': '#804e15',
    '--el-color-warning-light-3': '#b78140',
    '--el-color-warning-light-5': '#cd9f6f',
    '--el-color-warning-light-7': '#e0bd9f',
    '--el-color-warning-light-8': '#ead1ba',
    '--el-color-warning-light-9': '#f4e6d5',
    '--el-color-danger': '#8b1a1a',
    '--el-color-danger-dark-2': '#6f1515',
    '--el-color-danger-light-3': '#a34141',
    '--el-color-danger-light-5': '#b97070',
    '--el-color-danger-light-7': '#d0a0a0',
    '--el-color-danger-light-8': '#dcbcbc',
    '--el-color-danger-light-9': '#eed9d9',
    '--el-color-info': '#57534e',
    '--el-color-info-dark-2': '#46423e',
    '--el-color-info-light-3': '#7d7872',
    '--el-color-info-light-5': '#a3a09b',
    '--el-color-info-light-7': '#c9c6c2',
    '--el-color-info-light-8': '#dcdad7',
    '--el-color-info-light-9': '#efedeb',
    // 文字 / 背景 / 边框 / 填充(羊皮纸色系)
    '--el-text-color-primary': '#3b2f2f',
    '--el-text-color-regular': '#57493f',
    '--el-text-color-secondary': '#7d6b57',
    '--el-bg-color': '#faf4e2',
    '--el-bg-color-overlay': '#faf4e2',
    '--el-bg-color-page': '#f3ead3',
    '--el-border-color': '#c9b382',
    '--el-border-color-light': '#d8c69f',
    '--el-border-color-lighter': '#e7dbbd',
    '--el-border-color-extra-light': '#f0e7d2',
    '--el-fill-color': '#f0e6c8',
    '--el-fill-color-dark': '#e8dbb9',
    '--el-fill-color-light': '#f4ecd6',
    '--el-fill-color-lighter': '#f9f3e4',
    '--el-fill-color-blank': '#faf4e2',
    // 圆角 / 字体 / 开关激活色
    '--el-border-radius-base': '2px',
    '--el-border-radius-small': '2px',
    '--el-font-family': "Georgia, 'Times New Roman', 'STZhongsong', 'KaiTi', serif",
    '--el-switch-on-color': '#a5803a',
  },
  rootClass: 'bg-[#f3ead3] text-[#3b2f2f] border border-[#c9b382]',
  bannerClass: 'bg-[#2a1d10] text-[#e3c36b] border border-[#c9b382]',
  colors: ['#a5803a', '#faf4e2', '#f3ead3', '#3b2f2f'],
  seal: '魔',
  atmosphere: {
    // 羊皮纸: 多处赭色晕染叠出陈年渍痕, 与暖纸底自然咬合
    backgroundImage:
      'radial-gradient(58% 42% at 12% 6%, rgba(122, 86, 30, 0.16) 0%, transparent 62%),'
      + 'radial-gradient(44% 38% at 90% 20%, rgba(122, 86, 30, 0.12) 0%, transparent 66%),'
      + 'radial-gradient(70% 50% at 46% 104%, rgba(90, 64, 24, 0.1) 0%, transparent 68%)',
  },
}

/** 数字花园: 草木绿主色 + 米纸底色 + 衬线字体, Brad Woods 数字花园可视化技巧演示 */
const bradGarden: PlaygroundTheme = {
  key: 'brad_garden',
  name: '数字花园',
  desc: '草木绿主色、米纸底色、纸张质感，汇集 blend-modes/3D/描线等可视化技巧的温室。',
  path: '/template/playground/brad_garden',
  vars: {
    // 主色(草木绿)及明暗梯度
    '--el-color-primary': '#4a7c59',
    '--el-color-primary-dark-2': '#3b6447',
    '--el-color-primary-light-3': '#6f9579',
    '--el-color-primary-light-5': '#93b39b',
    '--el-color-primary-light-7': '#bcd2c2',
    '--el-color-primary-light-8': '#d3e2d7',
    '--el-color-primary-light-9': '#eaf2ec',
    // 功能色梯度(苔绿 / 麦黄 / 陶红)
    '--el-color-success': '#2f7d4f',
    '--el-color-success-dark-2': '#26643f',
    '--el-color-success-light-3': '#589671',
    '--el-color-success-light-5': '#8ab498',
    '--el-color-success-light-7': '#b8d2c0',
    '--el-color-success-light-8': '#cfe2d5',
    '--el-color-success-light-9': '#e6f0e9',
    '--el-color-warning': '#b08a3e',
    '--el-color-warning-dark-2': '#8d6e31',
    '--el-color-warning-light-3': '#c2a468',
    '--el-color-warning-light-5': '#d3bd8f',
    '--el-color-warning-light-7': '#e3d5b4',
    '--el-color-warning-light-8': '#ede2cb',
    '--el-color-warning-light-9': '#f6f0e2',
    '--el-color-danger': '#a35454',
    '--el-color-danger-dark-2': '#824343',
    '--el-color-danger-light-3': '#b87676',
    '--el-color-danger-light-5': '#cd9898',
    '--el-color-danger-light-7': '#e0baba',
    '--el-color-danger-light-8': '#ebcfcf',
    '--el-color-danger-light-9': '#f5e5e5',
    '--el-color-info': '#6e7566',
    '--el-color-info-dark-2': '#585e52',
    '--el-color-info-light-3': '#8b9184',
    '--el-color-info-light-5': '#a8ada2',
    '--el-color-info-light-7': '#c5c8c0',
    '--el-color-info-light-8': '#d8dad4',
    '--el-color-info-light-9': '#eaebe6',
    // 文字 / 背景 / 边框 / 填充(米纸色系)
    '--el-text-color-primary': '#33392f',
    '--el-text-color-regular': '#4d5548',
    '--el-text-color-secondary': '#79806f',
    '--el-bg-color': '#faf8f1',
    '--el-bg-color-overlay': '#faf8f1',
    '--el-bg-color-page': '#f2efe6',
    '--el-border-color': '#cfc9b8',
    '--el-border-color-light': '#dcd7c8',
    '--el-border-color-lighter': '#e8e4d8',
    '--el-border-color-extra-light': '#f0ede4',
    '--el-fill-color': '#f0ede2',
    '--el-fill-color-dark': '#e8e4d6',
    '--el-fill-color-light': '#f3f0e7',
    '--el-fill-color-lighter': '#f8f5ee',
    '--el-fill-color-blank': '#faf8f1',
    // 圆角 / 字体 / 开关激活色
    '--el-border-radius-base': '6px',
    '--el-border-radius-small': '4px',
    '--el-font-family': "Georgia, 'Noto Serif SC', 'STZhongsong', 'KaiTi', serif",
    '--el-switch-on-color': '#4a7c59',
  },
  rootClass: 'bg-[#f2efe6] text-[#33392f] border border-[#cfc9b8]',
  bannerClass: 'bg-[#2f3a2c] text-[#e4ecd8] border border-[#cfc9b8]',
  colors: ['#4a7c59', '#faf8f1', '#f2efe6', '#33392f'],
  seal: '园',
  atmosphere: {
    // 温室: 草木绿晕 + 麦黄暖斑, 模拟阳光穿过叶隙的花房光
    backgroundImage:
      'radial-gradient(56% 40% at 8% 4%, rgba(74, 124, 89, 0.14) 0%, transparent 64%),'
      + 'radial-gradient(48% 36% at 92% 16%, rgba(176, 138, 62, 0.12) 0%, transparent 66%),'
      + 'radial-gradient(64% 46% at 40% 100%, rgba(74, 124, 89, 0.1) 0%, transparent 70%)',
  },
}

/** 中式水墨: 浓墨主色 + 朱砂点缀 + 宣纸底 + 楷体, 留白与笔触构成的东方气韵 */
const ink: PlaygroundTheme = {
  key: 'ink',
  name: '中式水墨',
  desc: '浓墨为骨、朱砂为印、宣纸为底，留白与枯笔构成的东方气韵。',
  path: '/template/playground/ink',
  vars: {
    // 主色(墨色)及明暗梯度 —— 墨分五色, 由焦到淡
    '--el-color-primary': '#33403a',
    '--el-color-primary-dark-2': '#2a352f',
    '--el-color-primary-light-3': '#707975',
    '--el-color-primary-light-5': '#99a09d',
    '--el-color-primary-light-7': '#c2c6c4',
    '--el-color-primary-light-8': '#d6d9d7',
    '--el-color-primary-light-9': '#ebeceb',
    // 功能色梯度(青竹 / 赭石 / 朱砂 / 墨灰)
    '--el-color-success': '#4d6a4f',
    '--el-color-success-dark-2': '#3e5540',
    '--el-color-success-light-3': '#829784',
    '--el-color-success-light-5': '#a6b5a7',
    '--el-color-success-light-7': '#cad3cb',
    '--el-color-success-light-8': '#dce2dc',
    '--el-color-success-light-9': '#eff2ef',
    '--el-color-warning': '#9c6b3d',
    '--el-color-warning-dark-2': '#7d5631',
    '--el-color-warning-light-3': '#ba9777',
    '--el-color-warning-light-5': '#cdb59e',
    '--el-color-warning-light-7': '#e1d3c4',
    '--el-color-warning-light-8': '#ebe1d6',
    '--el-color-warning-light-9': '#f5f0ea',
    '--el-color-danger': '#a8462f',
    '--el-color-danger-dark-2': '#8c3a27',
    '--el-color-danger-light-3': '#c27d6d',
    '--el-color-danger-light-5': '#d4a297',
    '--el-color-danger-light-7': '#e5c7c0',
    '--el-color-danger-light-8': '#eedad3',
    '--el-color-danger-light-9': '#f6ece7',
    '--el-color-info': '#5f6661',
    '--el-color-info-dark-2': '#4f554f',
    '--el-color-info-light-3': '#8f9490',
    '--el-color-info-light-5': '#afb3b0',
    '--el-color-info-light-7': '#cfd2d0',
    '--el-color-info-light-8': '#dfe1df',
    '--el-color-info-light-9': '#eff0ef',
    // 文字 / 背景 / 边框 / 填充(宣纸色系)
    '--el-text-color-primary': '#2b332e',
    '--el-text-color-regular': '#47504a',
    '--el-text-color-secondary': '#6d756e',
    '--el-bg-color': '#fcf9f0',
    '--el-bg-color-overlay': '#fefcf6',
    '--el-bg-color-page': '#f2eee2',
    '--el-border-color': '#d0c8b6',
    '--el-border-color-light': '#ded7c7',
    '--el-border-color-lighter': '#ebe5d7',
    '--el-border-color-extra-light': '#f3efe4',
    '--el-fill-color': '#f0ece0',
    '--el-fill-color-dark': '#e8e3d4',
    '--el-fill-color-light': '#f4f1e7',
    '--el-fill-color-lighter': '#f9f6ee',
    '--el-fill-color-blank': '#fcf9f0',
    // 圆角 / 字体 / 开关激活色(朱砂)
    '--el-border-radius-base': '3px',
    '--el-border-radius-small': '2px',
    '--el-font-family': "'Noto Serif SC', 'Songti SC', 'STZhongsong', 'KaiTi', serif",
    '--el-switch-on-color': '#a8462f',
  },
  rootClass: 'bg-[#f2eee2] text-[#2b332e] border border-[#d0c8b6]',
  bannerClass: 'bg-[#232b26] text-[#f0e9d8] border border-[#3a423c]',
  colors: ['#33403a', '#fcf9f0', '#f2eee2', '#a8462f'],
  seal: '墨',
  atmosphere: {
    // 宣纸: 焦墨自左上洇开, 右下压一道淡墨收气, 右上一点朱砂余韵
    backgroundImage:
      'radial-gradient(52% 38% at 2% 0%, rgba(51, 64, 58, 0.18) 0%, transparent 62%),'
      + 'radial-gradient(38% 30% at 98% 8%, rgba(168, 70, 47, 0.09) 0%, transparent 68%),'
      + 'radial-gradient(64% 44% at 60% 102%, rgba(51, 64, 58, 0.13) 0%, transparent 70%)',
    mixBlendMode: 'multiply',
  },
}

/** 全部可选主题(新增主题在此追加) */
export const playgroundThemes: PlaygroundTheme[] = [business, harryPotter, bradGarden, ink]
