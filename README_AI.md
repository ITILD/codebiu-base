# codebiu_base — AI 协作指南

> 本文件是 AI 编码助手与新人开发者的**唯一入口地图**：项目是什么、怎么扩展、每一步放什么文档。
> 项目定位与快速开始见 [README.md](README.md)；详细规范在 `doc/doc_ch/`（见文末文档地图）。

## 1. 项目定位

**基线项目 = 公共底座**。保留用户注册登录 / 权限管理 / 文件系统 / 字典 / 动态配置 / AI 模型接入 / RAG / 任务队列等通用能力，作为后续场景的起步架子：

- `AGENT` — AI 智能体应用
- `CADGIS` — CAD/GIS 二三维专业应用
- `NOVEL` — 小说站等大众娱乐应用
- 其他场景按同模式扩展

扩展原则：**以新增模块扩展场景，不污染公共底座；禁 500MB+ 大库，模型能力走在线服务接入。**

## 2. 技术栈与目录

- **后端** `code/backend/server_py`：Python 3.13（强制新类型语法 `X | None`）+ FastAPI + SQLAlchemy 2.0 异步 + SQLModel + PostgreSQL/SQLite + **LanceDB**（唯一向量库）+ Redis/Fakeredis + Celery
- **前端** `code/frontend/vue3`：Vue 3.5 + TS + Vite(rolldown) + Element Plus + UnoCSS + Pinia + unplugin 全家桶（vue-router 文件路由 / auto-import / vue-components / icons）；图表 echarts，三维 babylonjs；页面与组件按业务模块垂直切分
- **零依赖本地组合**：SQLite + Fakeredis + LanceDB（不装外部服务即可启动）

```
code/backend/server_py/src/
├── common/            # 公共层: 配置中心(db/log/net)/动态配置/数据库封装/工具
├── module_main/       # 字典/健康检测/数据监测/通用动态配置
├── module_authorization/  # 注册登录(邮箱验证开关)/用户角色部门/Casbin RBAC
├── module_file/       # 虚拟文件树/local+S3 上传下载
├── module_ai/         # 模型配置/LLM/重排/OCR/在线语音 (仅接入, 不含本地推理)
├── module_rag/        # 知识库: 项目/文档/分块/授权/AG-UI 流式问答
├── module_agent/      # AI 助手: Agent 配置/Skill 注册表/手工 tool-calling 执行循环(AG-UI 流式)
├── module_office/     # 文档解析(仅 MinerU 外部服务调用, 工厂接口可扩展其他服务), 库模式无路由
├── module_task/       # 任务队列(local 协程 + Celery 双引擎)
├── module_contact/    # 联系触达: 验证码收发 + 通知中心(站内信必达+邮件/短信按订阅路由)
└── module_template/   # 新模块脚手架示例(CRUD/组件选型/布局/Babylon 3D)

# 每个业务线模块标准结构(五件套齐全 + utils):
module_<业务线>/
├── controller/        # 路由端点(参数校验+调 service)
├── service/           # 业务逻辑; 复杂跨模块业务 = service 之间互相调用
├── dao/               # 数据访问(关系库/向量库)
├── do/                # 表模型 + 请求响应体
├── dependencies/      # FastAPI 依赖注入
└── utils/             # 非业务算法与纯工具函数(不依赖业务状态)
```

前端按业务垂直切分，与后端模块一一对应（删模块文件夹即删整个功能）：

```
frontend/vue3/src/
├── common/             # 全局公共: api(http/httpError/authFetch)/components(自动注册)/composables/enums/i18n/stores/types/utils
├── app/                # 应用壳: layout 与设置面板组件(自动注册)/composables/config(menu.ts, versions)
├── modules/<模块>/     # {api, components, pages, types} 垂直聚合; 组件显式 import
└── pages/              # 全局页面: index.vue(toC主应用首页+登录) / admin.vue(toB后台工作台) / setting / version / 404
```

## 3. 工作流：从需求到代码（必读，一图记住）

```
用户提需求 → ① AI填卡+登记册加行(草案) → ② 人批准(唯一必做动作) → ③ AI开发 → ④ 交付登记
```

**核心门禁：状态 =「已批准」才能开发。** 状态只有 4 个：草案 / 已批准 / 已交付 / 已废弃。

| 步骤 | 动作 | 文档落点 |
| :--- | :--- | :--- |
| ① 登记 | AI 全自动：填一张需求卡 + 登记册加行 | [03-设计文档/00-需求功能登记册.md](doc/doc_ch/03-设计文档/00-需求功能登记册.md) + [99-需求卡模板](doc/doc_ch/03-设计文档/99-需求卡模板.md) |
| ② 批准 | **人一次对话确认**（"同意/可以"即算）→ 置「已批准」 | [04-规范/需求与功能管理.md](doc/doc_ch/04-规范/需求与功能管理.md) |
| ③ 开发 | AI 按手册实现（后端/前端接入清单），全程遵守代码规范 | [04-规范/开发流程.md](doc/doc_ch/04-规范/开发流程.md) + [代码规范.md](doc/doc_ch/04-规范/代码规范.md) |
| ④ 交付 | 验收标准逐条勾选 → 登记册与卡置「已交付」 | 登记册 + 需求卡 |

**AI 默认全自动**：用户提需求后 AI 填卡→给方案请求批准→批准后开发→交付；用户只需在第 ② 步说"批准"。
**豁免**（不占编号，不开卡）：缺陷修复、文档、纯重构、依赖升级——登记册「变更记录」表记一行。

## 4. 架构硬规则

1. Python 3.13 新类型语法（禁 `typing.Optional/Union/List`），async 优先，重库惰性 import。
2. **每个业务线模块必须有完整的 controller/service/dao/do/dependencies 五件套**；非业务算法放模块 `utils/`；业务逻辑只写 service，controller 只做参数校验与调度。
3. 模块间禁止互引 controller/dao/do 等内部文件；**复杂业务依靠 service 之间调用实现**；通用能力下沉 `common/`（后端）或 `src/common/`（前端）。
4. 权限点 `域:资源:动作`，前后端声明必须一致（`config/permissions.py` ↔ `menu.ts`）。
5. 业务可热更配置进动态配置中心（`sys_config` + schema 即表单）；引导配置进 config.yaml；**config.yaml 为入 git 的基线模板，严禁提交任何真实密钥**（密钥位一律留空，只注释 `to set real key`）；真实密钥只放 `config.<APP_ENV>.yaml`（gitignored，默认不存在，**开发时需自建 `config.dev.yaml`**，参考同目录注释示例）或 `CODEBIU_*` 环境变量。
6. 向量表继承 `VectorModel`（LanceModel 不支持 dict 注解，聚合元数据存 JSON 字符串）。
7. 前端页面自动路由（`pages/` 下文件路径即路由，**入口 .vue 不可改名/移位**，拆分只动同模块 `components/`）；菜单接 menu.ts；API 统一走 `common/api/http.ts`（流式/Blob 用 `authFetch.ts`，FastAPI 错误解析走 `httpError.ts`）；列表页用 `useTableQuery`、新增/编辑对话框用 `useCrudDialog`、日期格式化用 `common/utils/datetime.ts`，**禁止在页面内重复实现这些公共能力**；对话框子组件约定 `defineExpose({ open })`、打开时重置防脏数据、props/emits 必须带类型。
8. 依赖变更先 grep 复用，再确认无 500MB+ 大库，最后两端同步（pyproject / package.json）。

## 5. 关键文件索引

### 后端

| 文件 | 说明 |
| :--- | :--- |
| `src/app.py` | 服务入口 + **模块 router 注册中心**（新模块必须在此 import） |
| `src/app_task.py` | Celery Worker 入口（tasks.engine=celery 时需要；定时任务另启 `celery -A src.app_task beat`） |
| `src/module_task/tasks/scheduler.py` + `schedule_beat.py` | 周期调度(REQ-012)：local 单协程调度循环 / celery beat 每分钟 tick，调度定义落库热更（详见 deveops/运维手册/任务与调度运维.md） |
| `src/module_contact/service/notification.py` | 通知中心统一入口(REQ-011)：`notify(user_id, notify_type, title, content)` 站内必达 + 邮件/短信按订阅路由；任务终态埋点见 `module_task/tasks/__init__.py` |
| `src/module_agent/service/runner.py` | Agent 执行循环(REQ-013)：`chat_stream` 手工 tool-calling（bind_tools→astream→skill 执行回填→续跑，8 轮上限）；Skill 注册表见 `module_agent/skills/`（增删 skill 零改循环） |
| `login_security` 动态配置组 + `src/module_authorization/service/login_security.py` | 登录安全(REQ-014)：失败锁定/密码强度/二次验证参数管理员通用配置页可调即改即生效（默认锁 5 次/15 分钟）；失败计数走缓存键 TTL 到期自动恢复 |
| `GET /file/filesystem/preview/{entry_id}` + 前端 `modules/file/components/FilePreviewDialog.vue` | 文件在线预览(REQ-016)：鉴权同下载判定链，服务端流式代理(inline + RFC5987)规避对象存储跨域；前端 file-viewer 浏览器端渲染(依赖 @file-viewer/vue3，渲染器 6 件显式限定独立 chunk 按需懒加载，白名单见组件内 PREVIEWABLE_EXTENSIONS；不含 .ppt 老格式——其链路 16M CJK 字体) |
| `src/common/config/lifespan.py` | 启动流程（连接/建表/种子/权限初始化） |
| `src/common/config/db.py` | 数据库管理器（关系/缓存/向量装配） |
| `src/common/config/dynamic/schemas.py` | 动态配置组 schema（通用配置页由它驱动） |
| `src/common/utils/db/session/impl/db_vector_lancedb.py` | LanceDB 封装（建表/检索/谓词删除/重向量化） |
| `src/module_authorization/config/permissions.py` | sys/main 域权限声明 |
| `src/module_rag/config/permissions.py` | rag/task 域权限声明 |
| `config.yaml` / `config.<APP_ENV>.yaml` | 基线层(零依赖默认, 单文件可启动; **入 git，严禁真实密钥，只留 to-set-real-key 占位**) / 环境层(数据库/模型种子/真实密钥, gitignored; **默认不存在，开发时自建 `config.dev.yaml`**) |
| `alembic/`、`alembic.ini`、`src/common/utils/db/migration.py` | 数据库结构迁移(REQ-008)：首启 create_all+自动 stamp；演进 `alembic revision --autogenerate` + `upgrade head`(详见 deveops/运维手册/数据库运维.md) |
| `doc/dev/permission.md` | 新模块权限接入指南 |

### 前端

| 文件 | 说明 |
| :--- | :--- |
| `vite.config.ts` | **extendRoute 路由主题约定**（app/admin/standalone）+ 自动导入范围（common/app 组件全局注册，模块组件显式 import）+ 分包 |
| `src/app/config/menu.ts` | 全局菜单/权限/主应用入口卡数据源 |
| `src/common/api/http.ts` | fetch 封装（token 注入/401 单飞刷新重试） |
| `src/common/api/authFetch.ts` + `httpError.ts` | 原生 fetch 助手（流式/Blob 自动带令牌）+ FastAPI 错误解析共享层 |
| `src/common/api/aguiStream.ts` | AG-UI 流式事件（RAG 问答） |
| `src/common/composables/useTableQuery.ts` / `useCrudDialog.ts` | 分页列表查询 / 新增编辑对话框统一 composables（新 CRUD 页面必须复用，禁手写重复逻辑） |
| `src/common/utils/datetime.ts` | 日期时间格式化统一工具（formatDate/formatDateTime/formatTimeShort） |
| `src/pages/admin.vue` / `index.vue` | toB 后台工作台 / toC 主应用首页 |
| `src/modules/template/` | 组件选型参考（element-plus / echarts / babylonjs 基础用法） |

## 6. 常用命令

```bash
# 后端
cd code/backend/server_py
uv sync                 # 安装依赖
python src/app.py       # 启动 → http://127.0.0.1:2001/docs
python -m pytest tests -x   # 测试

# 前端
cd code/frontend/vue3
pnpm i
pnpm run dev            # 开发 → http://localhost:2002（端口取 .env 的 VITE_PORT）
pnpm vitest run         # 单元测试（配置在 vitest.config.ts，用例 src/**/*.spec.ts）
pnpm run build          # 构建（含 type-check: vue-tsc）

# 默认管理员: admin / admin123（config.yaml admin 段）
```

## 7. 变更自检清单（AI 修改代码后）

- [ ] 功能在登记册为「已批准」状态（豁免类除外）
- [ ] 后端新模块 → `app.py` 已注册；权限点已声明且前后端一致
- [ ] 新表/向量表可自动创建；动态配置（如有）schema 已声明
- [ ] 前端新页面 → menu.ts 已加；CRUD 复用 useTableQuery/useCrudDialog（对话框拆同模块 components/，`defineExpose({ open })`）；`pnpm run build` 通过；后端 `import app` 无报错
- [ ] 代码符合 [代码规范](doc/doc_ch/04-规范/代码规范.md)（新类型语法/中文注释/分层/惰性加载）
- [ ] 登记册与需求卡状态已同步；涉及文档已更新

## 8. 文档地图

| 位置 | 内容 | 何时读 |
| :--- | :--- | :--- |
| [README.md](README.md) | 项目定位/快速开始/能力总览 | 第一次接触项目 |
| `doc/doc_ch/01-入门/` | 环境搭建（技术基础/数据库/IDE） | 新人配环境 |
| `doc/doc_ch/02-开发指南/` | 大模型调用/后端/前端/权限体系/内存优化 | 开发中查阅 |
| `doc/doc_ch/03-设计文档/` | **需求功能登记册**/需求分析/总体架构/权限设计 + 需求卡模板 | 需求登记与评审 |
| `doc/doc_ch/04-规范/` | **需求与功能管理**/**开发流程**/**代码规范**/响应式规范/版本管理 | 开发全程 |
