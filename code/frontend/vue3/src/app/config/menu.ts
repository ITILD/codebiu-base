/**
 * 全局菜单配置(RuoYi 式目录)
 * 共用方: SysSidebar(后台侧边栏) / SysBreadcrumb(面包屑) / 首页入口卡 / 头像下拉
 *
 * 导航设计约定(全站统一, 新页面必须遵循):
 * 1. 所有需登录的功能页都以「后台侧边栏的分组 → 末级子项」平铺出现,
 *    页面内部不再自带页内导航(如 AI 助手 / 知识库管理 / 智能体编排同为 /ai 分组末级子项);
 * 2. 涉及系统本身的配置(权限、模型、监控、数据与配置等)标记 system,
 *    侧边栏以朱砂小标("系统" chip / 分组圆点)区分, 业务页面保持中性;
 * 3. 面向业务的末级页面标记 home, 会同时出现在首页入口卡: 从首页点击进入
 *    单页模式(homeLink 追加 ?bare=1), 不渲染后台侧边栏, 顶栏 Logo 返回首页;
 * 4. 新页面: 在对应分组 children 增加菜单项; 需在首页露出时加 home: true。
 */
import { markRaw } from 'vue'
import type { Component } from 'vue'
import {
  HomeFilled, UserFilled,
  Monitor, ChatDotRound, Setting,
  Files, Collection, FolderOpened,
  Timer, Search, MagicStick,
} from '@element-plus/icons-vue'

/** 末级菜单项(分组下的子项, 对应一个具体页面) */
export interface MenuLeaf {
  /** 路由路径(与 el-menu index 一致) */
  index: string
  title: string
  /** 权限码(缺省登录即可见) */
  perm?: string
  /** 系统级配置: 侧边栏显示"系统"小标并变色 */
  system?: boolean
  /** 首页入口卡展示(true 时从首页可直达该单页) */
  home?: boolean
  /** 是否在后台侧边栏展示(默认 true; false 表示仅首页入口) */
  admin?: boolean
  /** 首页入口卡图标(缺省取所属分组图标) */
  icon?: Component
  /** 首页入口卡描述(菜单不渲染) */
  desc?: string
}

/** 菜单项定义(无 children 的项自身即末级页面) */
export interface MenuItem extends Omit<MenuLeaf, 'index' | 'title'> {
  index: string
  title: string
  children?: MenuLeaf[]
}

/** 首页入口卡数据(由 home 末级页面展平而来) */
export interface HomeEntry {
  index: string
  title: string
  perm?: string
  icon?: Component
  desc?: string
  /** 所属分组标题(入口卡顶部小字) */
  groupTitle: string
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
    index: '/ai',
    icon: markRaw(ChatDotRound),
    title: 'AI 能力',
    desc: '对话、知识库与智能体编排, 以及模型与助手配置。',
    children: [
      // 三个使用页与系统配置页同为分组末级子项, 页面内不再有内页导航
      {
        index: '/rag/conversation',
        title: 'AI 助手',
        perm: 'rag:chat',
        home: true,
        icon: markRaw(ChatDotRound),
        desc: '与 AI 多轮对话, 引用知识库与联网结果。',
      },
      {
        index: '/rag/project',
        title: '知识库管理',
        perm: 'rag:project',
        home: true,
        icon: markRaw(Collection),
        desc: '管理知识库项目、文档与成员权限。',
      },
      {
        index: '/agent/manage',
        title: '智能体编排',
        perm: 'agent:manage',
        home: true,
        icon: markRaw(MagicStick),
        desc: '注册智能体、编排技能与全局视图。',
      },
      {
        index: '/ai/model_config',
        title: '模型配置',
        system: true,
        desc: '大模型 / OCR / 语音的统一接入与在线自测。',
      },
      {
        index: '/ai/assistant',
        title: 'AI 助手配置',
        system: true,
        desc: '助手展示形态、悬浮位置与默认能力。',
      },
    ],
  },
  {
    index: '/file',
    icon: markRaw(FolderOpened),
    title: '文件管理',
    perm: 'main:file',
    home: true,
    desc: '虚拟文件系统, 目录式浏览与秒传。',
  },
  {
    index: '/websearch',
    icon: markRaw(Search),
    title: '网页搜索',
    perm: 'websearch:search',
    desc: '多引擎网页搜索与连通性验证。',
    children: [
      {
        index: '/websearch/search',
        title: '搜索测试',
        perm: 'websearch:search',
        system: true,
        desc: '多引擎搜索与连通性验证。',
      },
    ],
  },
  {
    index: '/authorization',
    icon: markRaw(UserFilled),
    title: '权限管理',
    perm: 'sys',
    system: true,
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
    index: '/task',
    icon: markRaw(Timer),
    title: '任务队列',
    perm: 'task',
    system: true,
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
    system: true,
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
    system: true,
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

/** 后台侧边栏菜单(默认全部参与, 仅剔除显式 admin: false 的项) */
export const adminMenuItems: MenuItem[] = menuItems.filter((item) => item.admin !== false)

/** 首页入口卡(由标记 home 的末级页面展平, 保持菜单顺序) */
export const homeEntries: HomeEntry[] = menuItems.flatMap((group): HomeEntry[] => {
  if (group.children) {
    return group.children
      .filter((leaf) => leaf.home && leaf.admin !== false)
      .map((leaf) => ({
        index: leaf.index,
        title: leaf.title,
        perm: leaf.perm,
        icon: leaf.icon ?? group.icon,
        desc: leaf.desc ?? group.desc,
        groupTitle: group.title,
      }))
  }
  return group.home
    ? [{
        index: group.index,
        title: group.title,
        perm: group.perm,
        icon: group.icon,
        desc: group.desc,
        groupTitle: group.title,
      }]
    : []
})

/** 首页入口链接: bare=1 进入单页模式(不渲染后台侧边栏) */
export function homeLink(path: string) {
  return { path, query: { bare: '1' } }
}

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
