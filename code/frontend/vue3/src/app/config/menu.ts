/**
 * 全局菜单配置(RuoYi 式目录)
 * 共用方: SysSidebar(后台侧边栏) / SysBreadcrumb(面包屑) / 主页主应用入口卡 / 头像下拉
 * 菜单分两类:
 * - 主应用(mainApp: true): 知识库, 从首页直接进入, 无侧边栏,
 *   模块内孙页面导航由各模块页面自行承担
 * - 后台管理(其余): 仅经头像下拉"后台管理"入口进入, 显示侧边栏
 * 分组与后端 module_* 一一对应: authorization/rag/ai/file/main
 */
import { markRaw } from 'vue'
import type { Component } from 'vue'
import {
  HomeFilled, UserFilled,
  Monitor, ChatDotRound, Setting,
  Files, Collection, FolderOpened,
  Timer, Search,
} from '@element-plus/icons-vue'

/** 菜单项定义(perm 为权限码:与后端模块权限声明一致;缺省表示登录即可见) */
export interface MenuItem {
  /** 路由路径(与 el-menu index 一致) */
  index: string
  icon?: Component
  title: string
  /** 权限码(缺省登录即可见) */
  perm?: string
  /** 主页模块入口卡的描述文案(菜单不渲染) */
  desc?: string
  /** 主应用标记: 从首页直接进入的前台应用, 不进后台侧边栏 */
  mainApp?: boolean
  children?: { index: string; title: string; perm?: string }[]
}

export const menuItems: MenuItem[] = [
  {
    index: '/',
    icon: markRaw(HomeFilled),
    title: '首页',
  },
  {
    index: '/admin',
    icon: markRaw(Monitor),
    title: '系统概览',
    desc: '系统运行状态、快捷入口与最近访问。',
  },
  {
    index: '/authorization',
    icon: markRaw(UserFilled),
    title: '权限管理',
    perm: 'sys',
    desc: '用户、角色、部门与权限策略管理。',
    children: [
      { index: '/authorization/user', title: '用户管理', perm: 'sys:user' },
      { index: '/authorization/role', title: '角色管理', perm: 'sys:role' },
      { index: '/authorization/dept', title: '部门管理', perm: 'sys:dept' },
      { index: '/authorization/permission', title: '权限配置', perm: 'sys:permission' },
      { index: '/authorization/casbin', title: '策略规则', perm: 'sys:casbin' },
    ],
  },
  {
    index: '/rag',
    icon: markRaw(Collection),
    title: 'AI 助手',
    perm: 'rag',
    mainApp: true,
    desc: 'AI 的最终使用界面: 对话、知识库与智能体编排同级。',
    children: [
      // 首页入口卡取 children[0] 跳转, AI 助手为主入口(知识库/助手切换在对话页工具栏)
      { index: '/rag/conversation', title: 'AI 助手', perm: 'rag:chat' },
      { index: '/rag/project', title: '知识库管理', perm: 'rag:project' },
      // 智能体编排与知识库管理同级(统一由 AI 助手内页导航进入)
      { index: '/agent/manage', title: '智能体编排', perm: 'agent:manage' },
    ],
  },
  {
    index: '/websearch',
    icon: markRaw(Search),
    title: '网页搜索',
    perm: 'websearch:search',
    desc: '多引擎网页搜索与连通性验证。',
    children: [
      { index: '/websearch/search', title: '搜索测试', perm: 'websearch:search' },
    ],
  },
  {
    index: '/ai',
    icon: markRaw(ChatDotRound),
    title: 'AI 服务',
    desc: '模型统一配置与「打开即自测」；AI 助手形态与悬浮入口。',
    children: [
      { index: '/ai/model_config', title: '模型配置' },
      { index: '/ai/assistant', title: 'AI 助手配置' },
      // AI 助手三个使用页(独立布局, 自带内页导航): 后台侧边栏也提供直达入口,
      // 从后台进入后经顶栏头像下拉可回到后台管理
      { index: '/rag/conversation', title: 'AI 助手', perm: 'rag:chat' },
      { index: '/rag/project', title: '知识库管理', perm: 'rag:project' },
      { index: '/agent/manage', title: '智能体编排', perm: 'agent:manage' },
    ],
  },
  {
    index: '/file',
    icon: markRaw(FolderOpened),
    title: '文件管理',
    perm: 'main:file',
    desc: '虚拟文件系统,目录式浏览与秒传。',
  },
  {
    index: '/task',
    icon: markRaw(Timer),
    title: '任务队列',
    perm: 'task',
    desc: '异步任务提交、进度与重试管理。',
    children: [
      { index: '/task/queue', title: '任务列表', perm: 'task:queue' },
      { index: '/task/schedule', title: '定时任务', perm: 'task:schedule' },
    ],
  },
  {
    index: '/main',
    icon: markRaw(Setting),
    title: '数据与配置',
    desc: '数据概览、字段表、通用配置与研发工具。',
    children: [
      { index: '/main/overview', title: '数据概览', perm: 'main:db' },
      { index: '/main/db', title: '数据监测', perm: 'main:db' },
      { index: '/main/dict', title: '字段表管理', perm: 'main:dict' },
      { index: '/main/audit', title: '操作审计', perm: 'sys:audit' },
      { index: '/main/config', title: '通用配置', perm: 'main:config' },
      { index: '/main/codegen', title: '代码生成器', perm: 'sys:codegen' },
      { index: '/main/i18n', title: '多语言词条', perm: 'sys:i18n' },
    ],
  },
  {
    index: '/monitor',
    icon: markRaw(Monitor),
    title: '系统监控',
    desc: '前端状态与服务器硬件状态查看。',
    children: [
      { index: '/monitor/localstorage', title: '状态查看' },
      { index: '/monitor/server_status', title: '服务状态' },
    ],
  },
  {
    index: '/template',
    icon: markRaw(Files),
    title: '模板示例',
    desc: '布局容器等前端范例。',
    children: [
      { index: '/template/overview', title: '模板概览' },
      { index: '/template/playground', title: '组件选型' },
      { index: '/template/template', title: '模板管理' },
      { index: '/template/container', title: '布局容器' },
      { index: '/template/babylon', title: 'Babylon 3D' },
    ],
  },
]

/** 后台管理菜单(供侧边栏/头像下拉使用): 全量树剔除主应用分组 */
export const adminMenuItems: MenuItem[] = menuItems.filter((item) => !item.mainApp)

/** 主应用入口(供首页入口卡使用): 保持配置顺序展示 */
export const mainApps: MenuItem[] = menuItems.filter((item) => item.mainApp)

/**
 * 按路由路径精确匹配菜单树,返回面包屑轨迹 ['首页','分组','当前页']
 * - '/' 返回 [首页]; 无匹配(如 /setting)返回 [] → 面包屑不渲染
 * - 路径以分组 index 开头但无子项精确匹配时,返回 [分组](分组本身作为当前页)
 */
export function findMenuTrail(path: string): MenuItem[] {
  // 首页特殊处理
  if (path === '/') return [menuItems[0]]
  // 依次检查每个分组
  for (const group of menuItems) {
    if (group.index === '/') continue
    // 精确命中分组(无子项的直接入口,如 /file)
    if (group.index === path) return [menuItems[0], group]
    // 在子项中精确匹配
    const child = group.children?.find((c) => c.index === path)
    if (child) {
      // 构造携带标题的子项节点(面包屑只需 title)
      return [menuItems[0], group, { ...group, ...child, children: undefined, icon: undefined }]
    }
  }
  // 未收录的路径(如账户设置)不显示面包屑
  return []
}
