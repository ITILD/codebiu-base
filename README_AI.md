# codebiu_base — AI 协作指南（总入口）

> 本文件只保留**全局工作流与跨端规则**；后端/前端技术硬规则见 [后端 AI 规则](code/backend/server_py/README_AI.md) · [前端 AI 规则](code/frontend/vue3/README_AI.md)。项目定位见 [README.md](README.md)，文档分层见 [doc/README.md](doc/README.md)。

## 1. 项目定位

**基线项目 = 公共底座**，保留注册登录 / 权限 / 文件 / 字典 / 动态配置 / AI 模型接入 / RAG / 任务队列等通用能力：

- `AGENT` — AI 智能体应用
- `CADGIS` — CAD/GIS 二三维专业应用
- `NOVEL` — 小说站等大众娱乐应用
- 其他场景按同模式扩展

扩展原则：**新增模块扩展场景，不污染公共底座；禁 500MB+ 大库，模型能力走在线服务接入。**

## 2. 规则分层

| 层 | 文档 | 内容 |
| :--- | :--- | :--- |
| 全局 | 本文件 | 需求门禁、跨端边界、密钥、依赖、文档分层、交付自检 |
| 后端 | [server_py/README_AI.md](code/backend/server_py/README_AI.md) | Python 3.13、七类目录、分层职责、跨模块 service、配置/迁移、权限接入 |
| 前端 | [vue3/README_AI.md](code/frontend/vue3/README_AI.md) | 垂直模块、自动路由、HTTP 复用、列表/对话框、样式/响应式、菜单权限 |
| 运维 | [deveops/README.md](deveops/README.md) | 部署、首次初始化、跨版本数据库升级、回滚 |

同一规则只在一层写详细内容；根文件只做摘要 + 链接。

## 3. 工作流：从需求到代码

```
用户提需求 → ① AI填卡+登记册加行(草案) → ② 人批准(唯一必做动作) → ③ AI开发 → ④ 交付登记
```

**门禁：状态 =「已批准」才能开发。** 状态只有 4 个：草案 / 已批准 / 已交付 / 已废弃。

| 步骤 | 动作 | 文档落点 |
| :--- | :--- | :--- |
| ① 登记 | AI 全自动：填一张需求卡 + 登记册加行 | [00-需求功能登记册](doc/02-设计文档/00-需求功能登记册.md) + [99-需求卡模板](doc/02-设计文档/99-需求卡模板.md) |
| ② 批准 | **人一次对话确认**（"同意/可以"即算）→ 置「已批准」 | [需求与功能管理](doc/03-规范/需求与功能管理.md) |
| ③ 开发 | AI 按手册实现（后端/前端接入清单），遵守代码规范 | [开发流程](doc/03-规范/开发流程.md) + [代码规范](doc/03-规范/代码规范.md) |
| ④ 交付 | 验收标准逐条勾选 → 登记册与卡置「已交付」 | 登记册 + 需求卡 |

AI 默认全自动：填卡→给方案请批准→开发→交付，用户只在第 ② 步说"批准"。
豁免（不占编号，不开卡）：缺陷修复、文档、纯重构、依赖升级——登记册「变更记录」记一行。

## 4. 全局硬规则

1. **需求门禁**：功能必须「已批准」才写代码；无需求卡不得开工（豁免类除外）。
2. **公共底座保护**：优先新增模块/文件扩展场景；必须改公共底座时在需求卡写明影响面与兼容说明。
3. **跨端边界**：前后端权限码、接口契约、枚举必须一致；后端权限点 `域:资源:动作` ↔ 前端 `menu.ts`。
4. **模块化扩展**：后端新增 `module_xxx/`，前端新增 `src/modules/xxx/`；删除模块文件夹应能删除整个功能。
5. **密钥**：`config.yaml` 入 git 且**严禁真实密钥**；真实密钥只放 `config.dev.yaml`（gitignored）或 `CODEBIU_*` 环境变量。
6. **依赖**：先 grep 复用 → 确认无 500MB+ 大库 → 后端 `pyproject.toml` / 前端 `package.json` 同步登记 → 重库惰性加载/分包。
7. **数据库演进**：改表必须写 Alembic 增量脚本；启动只建缺失表/打基线，不自动 upgrade；生产升级前备份。
8. **文档分层**：跨端 → `doc/`；后端 → `server_py/doc/`；前端 → `vue3/doc/`；部署运维 → `deveops/`；禁止同一内容复制两份。
9. **交付同步**：代码、登记册状态、需求卡、相关文档一起更新；文档变更也在「变更记录」留痕。

## 5. 关键文件索引（跨端）

- **后端**：`src/app.py`（入口 + router 注册中心）、`src/common/config/lifespan.py`（启动初始化时序）、`alembic/versions/`（迁移脚本）、`config.yaml`（基线配置，入 git 无真实密钥）。
- **前端**：`vite.config.ts`（自动路由/导入/分包）、`src/app/config/menu.ts`（菜单/权限/首页入口唯一数据源）、`src/common/api/http.ts`（HTTP 封装）。
- **设计/运维**：`doc/02-设计文档/00-需求功能登记册.md`（需求台账与门禁）、`deveops/运维手册/配置与数据库初始化.md`（首次部署初始化）、`deveops/运维手册/版本升级与数据库迁移.md`（跨版本升级与回滚）。

各子项目完整索引见其 `README_AI.md` 与 `doc/README.md`。

## 6. 常用命令

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

## 7. 变更自检清单（AI 修改代码后）

- [ ] 功能在登记册为「已批准」状态（豁免类除外）
- [ ] 后端新模块 → `app.py` 已注册；权限点已声明且前后端一致
- [ ] 新表/新字段 → Alembic 迁移脚本已生成并审查；动态配置 schema 已声明
- [ ] 前端新页面 → `menu.ts` 已加；CRUD 复用 `useTableQuery` / `useCrudDialog`
- [ ] 前端 `pnpm run build` 通过；后端 `import app` 无报错
- [ ] 代码符合 [代码规范](doc/03-规范/代码规范.md) 与对应子项目 `README_AI.md`
- [ ] 登记册、需求卡、相关文档已同步；文档变更已记入「变更记录」

## 8. 文档地图

根文档按 01-入门 / 02-设计文档 / 03-规范 / 04-测试报告 分目录，完整导航（含「何时读」）见 [doc/README.md](doc/README.md)。
