/**
 * 版本信息数据源
 *
 * 基线项目按月发布的版本声明（路线图）：每月迭代一个版本节点，
 * 数组按"最新在前"排序，版本页时间线配合无限滚动分批渲染，避免一次性挂载全部条目。
 * 发版时在 versions 数组头部新增当月 VersionRecord，并同步 package.json version。
 */

/** 单条版本功能 */
export interface VersionFeature {
  /** 功能名称 */
  title: string
  /** 功能说明 */
  desc: string
}

/** 版本记录 */
export interface VersionRecord {
  /** 版本号 */
  version: string
  /** 版本主题名 */
  name: string
  /** 开发周期（展示用） */
  period: string
  /** 状态：released 已发布 / dev 开发中 */
  status: 'released' | 'dev'
  /** 一句话简介 */
  summary: string
  /** 亮点标签 */
  tags: string[]
  /** 功能明细 */
  features: VersionFeature[]
}

/** 项目介绍（版本页 Hero 区） */
export const projectIntro = {
  /** 项目名 */
  name: 'Codebiu',
  /** 标语 */
  tagline: '多平台快速开发部署基线项目',
  /** 项目简介 */
  description:
    '前后端分离 + 文档 + 运维一体化的项目模板：FastAPI + Vue3 基线开箱即用，' +
    '认证、权限、文件、数据库、AI 能力即插即用，新项目复制即起步。',
} as const

/** 主要功能列表（版本页 Hero 下方功能卡片） */
export const mainFeatures = [
  {
    icon: 'Lock',
    title: '权限体系',
    desc: 'Casbin 域分离 RBAC（菜单 / 按钮 / 接口）+ 项目级数据权限（成员 / 部门三档位）',
  },
  {
    icon: 'MagicStick',
    title: 'AI 能力',
    desc: 'LLM 流式对话、OCR、重排、语音 ASR/TTS、RAG 知识库（向量检索 + 意图分析）',
  },
  {
    icon: 'Files',
    title: '通用底座',
    desc: 'JWT 认证、文件系统（预签名 URL / 去重 / 引用计数）、多数据库、双引擎任务调度',
  },
  {
    icon: 'Compass',
    title: '双主题模板',
    desc: 'toB 后台管理（侧边栏工作台）+ toC 主应用（知识库前台）两套布局开箱即用',
  },
  {
    icon: 'SetUp',
    title: '工程化',
    desc: 'uv / pnpm 包管理、docker 开发部署、SQLite + Fakeredis + LanceDB 零依赖本地开发',
  },
] as const

/** 版本记录（最新在前，每月一个节点） */
export const versions: VersionRecord[] = [
  {
    version: 'v1.0.0',
    name: '基线抽取版',
    period: '2026-10',
    status: 'released',
    summary: '从真实项目抽取为精简基线：保留通用底座，剥离业务模块与重型依赖。',
    tags: ['基线', '瘦身', 'v1.0.0'],
    features: [
      { title: '注册登录', desc: 'JWT 认证 + 邮箱验证码注册（动态开关）+ 用户/角色/部门管理' },
      { title: '权限体系', desc: 'Casbin 域分离 RBAC，菜单/按钮/接口三层授权，前后端权限点一致' },
      { title: '通用底座', desc: '字典管理、动态配置中心（schema 即表单）、健康检测、数据监测、虚拟文件系统（本地/S3）' },
      { title: 'AI 能力', desc: '模型配置中心统一接入 LLM 对话/重排/OCR/在线语音 ASR/TTS，全部走外部服务' },
      { title: 'RAG 知识库', desc: '文档解析（MinerU 外部服务）→ 智能分块 → LanceDB 向量检索问答' },
      { title: '任务队列', desc: '本地协程 + Celery 双引擎任务调度，Worker 向量库自愈' },
      { title: '双主题模板', desc: 'toB 后台管理 + toC 主应用开箱即用，组件示例含 element-plus/echarts/babylonjs' },
      { title: '依赖精简', desc: '移除 torch 等大型推理依赖与 9 个业务模块，SQLite + Fakeredis + LanceDB 零依赖本地开发' },
    ],
  },
]
