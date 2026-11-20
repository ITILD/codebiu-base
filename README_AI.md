# codebiu_base — AI 协作指南（唯一入口）

> **本文件是 AI IDE 的唯一必读入口。** 无论使用哪款 AI IDE，开始任何任务前先读本文件，再读 [文档总索引](doc/README.md)，最后按任务进入对应端的 `README_AI.md`。
> 子规则：[后端 AI 规则](code/backend/server_py/README_AI.md) · [前端 AI 规则](code/frontend/vue3/README_AI.md) · [客户端 AI 规则](code/frontend/flutter/README_AI.md)。
> 项目定位见 [README.md](README.md)；文档分层归属与防冗余规则见 [doc/README.md](doc/README.md)；可拖入 AI IDE 的纯 Markdown 开发 Skill 见 [doc/05-开发skill/](doc/05-开发skill/README.md)。

## 0. 启动协议（AI 每次开工前执行）

1. **读入口**：本文件 → [doc/README.md](doc/README.md) → 对应端 `README_AI.md`。
2. **定主题**：本项目的架构主轴是 **Model / Skill / Agent 三层一等公民**；新功能先归类，再决定落地位置。
3. **查门禁**：需求是否已在 [需求功能登记册](doc/02-设计文档/00-需求功能登记册.md) 为「已批准」；未批准不得写功能代码（豁免类除外）。
4. **文档先行**：新需求必须先改 `doc/`（登记册 + 需求卡 + 设计/契约），再动代码。
5. **完成后同步**：代码、登记册、需求卡、设计文档、`doc/doc-manifest.yaml` 一起更新；外部/手工代码按 §5.3 回收。

## 1. 项目定位：AI 能力平台基线

**基线项目 = 以 AI 能力平台为核心的公共底座**，不是「带 AI 功能的业务系统」。平台只认三种一等公民：

| 层 | 放什么 | 形态 | 示例 |
| :--- | :--- | :--- | :--- |
| **Model** | 能力供给，不含业务逻辑 | `ai_model` / `static_func` | Qwen 主模型、bge embeddings、哈希/正则/校验器 |
| **Skill** | 单一工作技能，最小可复用执行单元 | `ai_skill` / `static_skill` / `hybrid` | `doc_parse`、`doc_chunk_index`、`sys.container_*` |
| **Agent** | 编排单元，完成一整套任务 | `ai_agent` / `static_agent` / `hybrid` | `builtin_thinking`、`kb_ingest_agent`、`ops_agent` |

- 依赖单向：`Agent → Skill → Model(可选) → Service`；Model 不调用任何东西，Skill 不互相编排，Agent 不调用 Agent。
- 三条入口一个运行时：Web Controller / Agent Tool Adapter / Celery Task Executor 全部汇合到 `SkillRuntime.invoke()`。
- 零模型可运行：`static_*` 能力在无模型配置时必须可运行；不强制使用 AI。
- 业务场景（`AGENT` / `CADGIS` / `NOVEL` / 其他）通过新增模块扩展，不污染公共底座。

权威契约：[04-AI能力平台架构设计](doc/02-设计文档/04-AI能力平台架构设计.md)；对话执行协议：[05-对话智能体与执行协议设计](doc/02-设计文档/05-对话智能体与执行协议设计.md)。

## 2. 规则分层

| 层 | 文档 | 内容 |
| :--- | :--- | :--- |
| 全局 | 本文件 | AI 启动协议、文档先行门禁、三层归类、代码-文档同步、密钥、依赖、交付自检 |
| 文档治理 | [doc/README.md](doc/README.md) | 文档分层唯一归属、跨层主题矩阵、防冗余规则、维护门禁（唯一事实来源） |
| 开发 Skill | [doc/05-开发skill/](doc/05-开发skill/README.md) | 纯 Markdown prompt skill：需求登记、三层归类、代码回收、同步巡检、模块骨架、交付验收 |
| 后端 | [server_py/README_AI.md](code/backend/server_py/README_AI.md) | Python 3.13、七类目录、分层职责、跨模块 service、配置/迁移、权限接入 |
| 前端 | [vue3/README_AI.md](code/frontend/vue3/README_AI.md) | 垂直模块、自动路由、HTTP 复用、列表/对话框、样式/响应式、菜单权限 |
| 客户端 | [flutter/README_AI.md](code/frontend/flutter/README_AI.md) | 四层单向依赖、provider 状态、SSE 流式、主题与多端壳 |
| 运维 | [deveops/README.md](deveops/README.md) | 部署、首次初始化、跨版本数据库升级、回滚 |

同一规则只在一层写详细内容；本文件只做摘要 + 链接。

## 3. 工作流：文档先行，代码后行

```
用户提需求
  → ① 文档先行：登记册加行 + 需求卡 + 设计/契约更新（草案）
  → ② 人批准（唯一必做动作）
  → ③ 代码开发（先归类三层，再按手册实现）
  → ④ 代码-文档同步 + 交付登记
```

**门禁：需求状态 =「已批准」且设计/契约已更新，才能写功能代码。** 状态只有 4 个：草案 / 已批准 / 已交付 / 已废弃。

| 步骤 | 动作 | 文档落点 |
| :--- | :--- | :--- |
| ① 文档先行 | AI 全自动：填需求卡 + 登记册加行 + 更新设计/契约（涉及三层时） | [00-需求功能登记册](doc/02-设计文档/00-需求功能登记册.md) + [99-需求卡模板](doc/02-设计文档/99-需求卡模板.md) + [04](doc/02-设计文档/04-AI能力平台架构设计.md)/[05](doc/02-设计文档/05-对话智能体与执行协议设计.md) |
| ② 批准 | **人一次对话确认**（"同意/可以/批准"即算）→ 置「已批准」 | [需求与功能管理](doc/03-规范/需求与功能管理.md) |
| ③ 开发 | AI 按手册实现，先过三层判定树，再写代码 | [开发流程](doc/03-规范/开发流程.md) + [代码规范](doc/03-规范/代码规范.md) |
| ④ 同步交付 | 验收标准逐条勾选 → 同步文档与清单 → 登记册与卡置「已交付」 | 登记册 + 需求卡 + `doc/doc-manifest.yaml` |

AI 默认全自动：文档先行 → 给方案请批准 → 开发 → 同步交付，用户只在第 ② 步说"批准"。
豁免（不占编号，不开卡）：缺陷修复、文档、纯重构、依赖升级——登记册「变更记录」记一行；**但涉及能力契约、接口、表结构、权限变化时仍必须同步文档**。

## 4. 全局硬规则

1. **需求门禁**：功能必须「已批准」才写代码；无需求卡不得开工（豁免类除外）。
2. **文档先行**：新需求先改 `doc/`（登记册 + 需求卡 + 设计/契约），再改代码；禁止「先写代码后补文档」。
3. **三层归类**：新功能先过 [04 §2.6 判定树](doc/02-设计文档/04-AI能力平台架构设计.md)。Model / Skill / Agent / 业务流程 / 普通 CRUD 必须显式归类；归类结果写进需求卡。
4. **公共底座保护**：优先新增模块/文件扩展场景；必须改公共底座时在需求卡写明影响面与兼容说明。
5. **跨端边界**：前后端权限码、接口契约、枚举必须一致；后端权限点 `域:资源:动作` ↔ 前端 `menu.ts`。
6. **模块化扩展**：后端新增 `module_xxx/`，前端新增 `src/modules/xxx/`；删除模块文件夹应能删除整个功能。
7. **密钥**：`config.yaml` 入 git 且**严禁真实密钥**；真实密钥只放 `config.dev.yaml`（gitignored）或 `CODEBIU_*` 环境变量。
8. **依赖**：先 grep 复用 → 确认无 500MB+ 大库 → 后端 `pyproject.toml` / 前端 `package.json` 同步登记 → 重库惰性加载/分包。
9. **数据库演进**：改表必须写 Alembic 增量脚本；启动只建缺失表/打基线，不自动 upgrade；生产升级前备份。
10. **文档分层**：归属层与跨层主题矩阵以 [文档总索引](doc/README.md) 为唯一事实来源（跨端 → `doc/`；后端 → `server_py/doc/`；前端 → `vue3/doc/`；客户端 → `flutter/doc/`；部署运维 → `deveops/`）；同一内容禁止复制两份，落盘后必须在该层导航登记。根展示页 `README.md` 与 `README.en.md` 为双语镜像，任何一侧的章节/截图/链接变更必须在同一次改动中同步另一侧。
11. **代码-文档同步**：关键代码入口带 `@doc-sync` 标记；契约/接口/表/权限变化必须同步 `doc/doc-manifest.yaml` 与对应设计文档。
12. **外部代码回收**：外部传入或手工修改的代码，合入前必须执行 §5.3 回收流程；无法映射到文档的代码不得合入公共底座。
13. **交付同步**：代码、登记册状态、需求卡、相关文档、`doc-manifest` 一起更新；文档变更也在「变更记录」留痕。

## 5. 代码-文档同步机制

文档与代码的漂移是基线项目最大的隐性成本。本仓库用 **「清单 + 标记 + Skill」三件套**把同步变成可执行流程，而不是靠记忆。

### 5.1 三件套

| 机制 | 位置 | 作用 |
| :--- | :--- | :--- |
| **机器可读清单** | [`doc/doc-manifest.yaml`](doc/doc-manifest.yaml) | 每份权威文档的层级、主题、对应代码路径、同步触发条件；AI 先查清单再改文档 |
| **代码标记** | 关键入口文件顶部 `@doc-sync: <文档路径>; 触发: <条件>` | 改代码时一眼看到「必须同步哪份文档」 |
| **同步 Skill** | [`doc/05-开发skill/03-代码导入与文档回收.md`](doc/05-开发skill/03-代码导入与文档回收.md) · [`04-文档代码同步巡检.md`](doc/05-开发skill/04-文档代码同步巡检.md) | 把回收/巡检步骤固化为可拖入 AI IDE 的 prompt |

### 5.2 何时必须同步

| 代码变化 | 必须同步的文档 |
| :--- | :--- |
| 新增/删除模块、路由挂载、权限声明 | [02-总体架构与功能设计](doc/02-设计文档/02-总体架构与功能设计.md)、后端 [02-目录结构](code/backend/server_py/doc/dev/02-目录结构.md)、前端 [05-权限与菜单](code/frontend/vue3/doc/dev/05-权限与菜单.md) |
| 新增/修改 Skill、Agent、Model 能力 | [04-AI能力平台架构设计](doc/02-设计文档/04-AI能力平台架构设计.md)、[05-对话智能体与执行协议设计](doc/02-设计文档/05-对话智能体与执行协议设计.md)、需求卡 |
| 接口契约、错误码、事件协议变化 | 对应端开发指南 + 需求卡 + 前端/客户端类型说明 |
| 新表/新字段/迁移脚本 | 后端 [04-数据库迁移](code/backend/server_py/doc/dev/04-数据库迁移.md)、设计文档数据模型、`doc-manifest` |
| 配置项/动态配置 schema 变化 | 后端 [03-配置与初始化](code/backend/server_py/doc/dev/03-配置与初始化.md)、运维配置手册 |
| 部署形态、队列、worker 变化 | [deveops](deveops/README.md)、[任务与调度运维](deveops/运维手册/任务与调度运维.md) |
| 对外定位/能力清单变化 | `README.md` + `README.en.md`（双语同步） |

### 5.3 外部/手工代码回收 SOP

外部传入或手工修改的代码，按以下顺序处理，**不得直接合入后再说**：

1. **盘点**：列出新增/修改/删除的文件，标出所属端与模块。
2. **归类**：按 [04 §2.6](doc/02-设计文档/04-AI能力平台架构设计.md) 判断是 Model / Skill / Agent / 业务流程 / CRUD。
3. **映射**：在 `doc/doc-manifest.yaml` 找到对应文档；找不到就新增映射，不允许「无主代码」。
4. **比对**：对照文档检查契约、接口、表结构、权限、配置是否一致；不一致时以「代码事实 + 设计意图」共同修正，不能只改一边。
5. **回写**：更新设计文档、需求卡、登记册变更记录；涉及展示页时同步中英文。
6. **验证**：按 [04-文档代码同步巡检](doc/05-开发skill/04-文档代码同步巡检.md) 跑链接、双语、清单一致性检查。
7. **留痕**：在登记册「变更记录」写一行，注明来源（外部/手工）、影响面、同步的文档。

### 5.4 AI 可识别内容规范

为了让不同 AI IDE 都能稳定识别，新增/修改文档时遵守以下约定：

- **Skill 文档**：`doc/05-开发skill/*.md` 使用 YAML frontmatter（`skill` / `name` / `triggers` / `inputs` / `outputs` / `gate`），正文只写可执行步骤。
- **清单**：`doc/doc-manifest.yaml` 字段固定为 `id / path / layer / authority_for / mirror / code / sync_triggers`。
- **代码标记**：统一写作 `@doc-sync: <相对路径>; 触发: <条件>`，放在文件头注释区，不参与运行。
- **单一来源**：同一规则只在归属层写详细内容；其他位置只放一行链接，避免 AI 读到互相冲突的版本。

## 6. 开发 Skill（doc/05-开发skill）

纯 Markdown prompt skill，不依赖脚本，任何 AI IDE 都能直接读取：

| Skill | 用途 |
| :--- | :--- |
| [01-需求登记与批准](doc/05-开发skill/01-需求登记与批准.md) | 把一句话需求变成登记册行 + 需求卡 + 批准请求 |
| [02-三层归类与文档先行](doc/05-开发skill/02-三层归类与文档先行.md) | 过判定树，先改设计/契约，再给开发方案 |
| [03-代码导入与文档回收](doc/05-开发skill/03-代码导入与文档回收.md) | 外部/手工代码合入前的映射与回写 |
| [04-文档代码同步巡检](doc/05-开发skill/04-文档代码同步巡检.md) | 定期检查链接、双语、清单与代码标记 |
| [05-模块骨架生成](doc/05-开发skill/05-模块骨架生成.md) | 按三层与七类目录生成后端/前端/客户端骨架 |
| [06-交付验收与发版](doc/05-开发skill/06-交付验收与发版.md) | 验收清单、登记册收口、版本记录 |

**使用方式**：把对应 `.md` 拖入 AI IDE 对话框，或在支持目录扫描的 IDE 中直接引用路径；随后在对话框补充本次任务细节即可。后期升级为带脚本的 skill 时，入口与流程保持不变。

## 7. 关键文件索引（跨端）

- **架构与治理**：`doc/02-设计文档/04-AI能力平台架构设计.md`（三层契约）、`doc/02-设计文档/05-对话智能体与执行协议设计.md`（执行协议）、`doc/README.md`（文档治理）、`doc/doc-manifest.yaml`（机器可读清单）、`doc/05-开发skill/`（开发 Skill）。
- **后端**：`src/app.py`（入口 + router 注册中心）、`src/common/config/lifespan.py`（启动初始化时序）、`alembic/versions/`（迁移脚本）、`config.yaml`（基线配置，入 git 无真实密钥）、`module_agent/`（SkillRuntime / Agent 编排）。
- **前端**：`vite.config.ts`（自动路由/导入/分包）、`src/app/config/menu.ts`（菜单/权限/首页入口唯一数据源）、`src/common/api/http.ts`（HTTP 封装）。
- **客户端**：`lib/common/app_core.dart`（组合根）、`lib/modules/ai/`（对话入口）、`lib/common/theme.dart`（主题与手机壳）。
- **设计/运维**：`doc/02-设计文档/00-需求功能登记册.md`（需求台账与门禁）、`deveops/运维手册/配置与数据库初始化.md`（首次部署初始化）、`deveops/运维手册/版本升级与数据库迁移.md`（跨版本升级与回滚）。

各子项目完整索引见其 `README_AI.md` 与 `doc/README.md`。

## 8. 常用命令

```bash
# 后端
cd code/backend/server_py
uv sync
python src/app.py            # http://127.0.0.1:6666/docs
uv run pytest tests -x
uv run alembic upgrade head

# 前端
cd code/frontend/vue3
pnpm i
pnpm run dev                 # http://localhost:8888
pnpm vitest run
pnpm run build

# 默认管理员: admin / admin123（config.yaml admin 段）
```

## 9. 变更自检清单（AI 修改代码后）

- [ ] 功能在登记册为「已批准」状态（豁免类除外）
- [ ] 已按 [04 §2.6](doc/02-设计文档/04-AI能力平台架构设计.md) 完成三层归类，并写入需求卡
- [ ] 新需求先改了 `doc/`（登记册 / 需求卡 / 设计或契约），再改代码
- [ ] 后端新模块 → `app.py` 已注册；权限点已声明且前后端一致
- [ ] 新表/新字段 → Alembic 迁移脚本已生成并审查；动态配置 schema 已声明
- [ ] 前端新页面 → `menu.ts` 已加；CRUD 复用 `useTableQuery` / `useCrudDialog`
- [ ] 前端 `pnpm run build` 通过；后端 `import app` 无报错
- [ ] 代码符合 [代码规范](doc/03-规范/代码规范.md) 与对应子项目 `README_AI.md`
- [ ] `@doc-sync` 标记指向的文档已同步；`doc/doc-manifest.yaml` 映射已更新
- [ ] 外部/手工代码已按 §5.3 完成回收，并在登记册「变更记录」留痕
- [ ] 登记册、需求卡、相关文档已同步；根展示页改动已双语镜像
- [ ] 新增/移动文档已登记到所属层导航，并通过 [文档总索引](doc/README.md) §6 的防冗余自检

## 10. 文档地图

文档体系共 5 层 + AI 规则层 + 开发 Skill 层，**分层归属、跨层主题矩阵、完整清单与防冗余规则全部见 [文档总索引](doc/README.md)**（唯一事实来源）：

| 层 | 入口 |
| :--- | :--- |
| 项目级 | [doc/README.md](doc/README.md)（总索引 / 需求台账 / 架构 / AI 三层 / 权限 / 规范 / 测试报告） |
| 开发 Skill | [doc/05-开发skill/README.md](doc/05-开发skill/README.md) |
| 后端 | [server_py/doc/README.md](code/backend/server_py/doc/README.md) |
| Web 前端 | [vue3/doc/README.md](code/frontend/vue3/doc/README.md) |
| 客户端 | [flutter/doc/README.md](code/frontend/flutter/doc/README.md) |
| 运维 | [deveops/README.md](deveops/README.md) |
| 展示页 | [README.md](README.md)（简中）· [README.en.md](README.en.md)（English，镜像同步） |
| 机器可读 | [doc/doc-manifest.yaml](doc/doc-manifest.yaml) |
