# codebiu_base

多平台快速开发部署基线项目：前后端分离 + 文档 + 运维一体化的项目模板，可作为新项目的起点复制扩展。

从真实项目抽取精简而来：保留「用户注册登录 / 权限管理 / 基础 AI + RAG / 文件管理 / 字典 / 主程序检测」等通用底座，
剥离具体业务模块与重型依赖（torch/transformers 等），让新项目零包袱起步。

## 仓库结构

```
codebiu_base/
├── code/
│   ├── backend/
│   │   └── server_py/    # 后端基线：Python 3.13 + FastAPI + SQLAlchemy 2.0(异步) + PostgreSQL/SQLite
│   └── frontend/
│       └── vue3/         # 前端基线：Vue3 + TypeScript + Vite + Element Plus + UnoCSS + Pinia
├── doc/doc_ch/           # 项目文档（中文）
└── deveops/              # 部署指南、运维脚本、运维手册（docker）
```

## 核心能力

| 域 | 能力 |
| :--- | :--- |
| **认证权限** | 注册登录（支持邮箱验证码开关）、JWT 双令牌、Casbin 域分离 RBAC（菜单/按钮/接口）、项目级数据权限（成员/部门三档位） |
| **AI** | 模型动态配置（按用户/部门隔离 public/dept/user）、LLM 流式对话、重排、OCR、语音 ASR/TTS（纯在线服务接入，无本地大模型） |
| **RAG** | 知识库项目/文档/成员/部门授权、文档解析（MinerU 外部服务调用，接口可扩展其他解析服务）、分块向量化（LanceDB）、意图分析问答 |
| **文件** | 虚拟文件树、上传下载、预签名 URL、秒传去重、引用计数、local/S3 存储切换 |
| **通用** | 字典管理、健康检测（CPU/内存/磁盘/网络）、数据监测、通用动态配置中心、双引擎任务调度（本地协程 + Celery） |
| **工程** | uv / pnpm 包管理、docker 开发部署、SQLite + Fakeredis + LanceDB 零依赖本地开发组合、两套前端主题模板（toB/toC） |

## 快速开始

```bash
# 后端（零依赖组合：SQLite + Fakeredis + LanceDB）
cd code/backend/server_py
uv sync
# 按需复制 config.dev.yaml 修改（默认即可启动）
python src/app.py            # http://127.0.0.1:2001/docs

# 前端
cd code/frontend/vue3
pnpm i
pnpm run dev                 # http://localhost:5173（代理 /base_server → 2001）
```

默认管理员：`admin / admin123`（见 `config.yaml` admin 段，首启入库后可在 通用配置页 修改）。

> - 大模型能力需在环境层 `config.dev.yaml`（或 通用配置页）填入真实 API Key（对话/向量化/重排等）。
> - 数据库 / docker 等环境安装详见 [开发环境配置](doc/doc_ch/01-入门/3-开发环境.md)。

## 前端两套主题模板

| 主题 | 入口 | 说明 |
| :--- | :--- | :--- |
| **toB 后台管理** | 登录后头像下拉「后台管理」→ `admin.vue` 工作台 | 侧边栏布局（SysSidebar + 面包屑），承载系统管理/文件/AI/知识库/任务/监控等后台页面 |
| **toC 主应用** | 首页 `index.vue` 入口卡 | 无侧边栏的独立前台（当前挂载知识库问答），适合面向终端用户的功能 |

菜单与权限由 `src/app/config/menu.ts` 统一驱动；路由 meta 约定见 `vite.config.ts` extendRoute。

## 新模块扩展指南

1. **后端**：复制 `src/module_template/` 为 `module_xxx/`（标准 controller/service/dao/do/dependencies 结构），在 `src/app.py` 注册 import，权限接入见 [permission.md](code/backend/server_py/doc/dev/permission.md)。
2. **前端**：在 `src/modules/` 下新建 `xxx/`（api/components/pages/types 聚合，路由自动生成），在 `src/app/config/menu.ts` 加菜单项。
3. 全流程详解见 [后端开发指南](doc/doc_ch/02-开发指南/2-后端开发.md) 与 [前端开发指南](doc/doc_ch/02-开发指南/3-前端开发.md)。

## 文档导航

| 目录 | 内容 |
| :--- | :--- |
| [README_AI.md](README_AI.md) | **AI 协作与新人的入口地图（需求→批准→开发工作流）** |
| [doc/doc_ch/](doc/doc_ch/README.md) | 文档总导航 |
| [01-入门](doc/doc_ch/01-入门/) | 技术基础、环境配置、IDE 插件 |
| [02-开发指南](doc/doc_ch/02-开发指南/) | 后端 / 前端开发、权限体系、大模型调用 |
| [03-设计文档](doc/doc_ch/03-设计文档/) | **需求功能登记册（批准门禁）**、需求分析、架构设计、权限设计 |
| [04-规范](doc/doc_ch/04-规范/) | **需求与功能管理**、开发流程、代码规范、版本管理 |
| [deveops](deveops/README.md) | 部署指南与运维 |

## 版本管理

- 后端版本记录：`code/backend/server_py/doc/tag_doc/`
- 前端版本时间线：`code/frontend/vue3/src/app/config/versions.ts`
- 基线当前版本：v1.0.0（基线抽取版）

## 贡献方式

分支 `dev` 开发，PR 审查后合入 `main`；遵循 [代码规范](doc/doc_ch/04-规范/代码规范.md) 与 [版本管理](doc/doc_ch/04-规范/版本管理.md)。
