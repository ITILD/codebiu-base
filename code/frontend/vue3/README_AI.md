# frontend/vue3 — AI 协作规则（前端分层）

> 全局工作流（需求 → 批准 → 开发 → 交付）见根 [README_AI.md](../../../README_AI.md)；本文件只约束前端代码与前端文档；后端规则见 [server_py/README_AI.md](../../backend/server_py/README_AI.md)；文档导航见 [doc/README.md](doc/README.md)。

## 1. 修改前必读

1. 功能在根 [需求功能登记册](../../../doc/02-设计文档/00-需求功能登记册.md) 为「已批准」（缺陷/文档/纯重构/依赖升级豁免）。
2. 先读 [01-开发指南](doc/dev/01-开发指南.md)，确认页面/API/类型落在哪个模块。
3. 写 UI 前读 [02-视觉主题规范](doc/dev/02-视觉主题规范.md) 与 [03-样式写入规范](doc/dev/03-样式写入规范.md)。
4. 自适应读 [04-响应式规范](doc/dev/04-响应式规范.md)；菜单/按钮权限读 [05-权限与菜单](doc/dev/05-权限与菜单.md)。

## 2. 硬规则（前端）

1. **垂直模块化**：业务代码进 `src/modules/<模块>/{api,components,pages,types}`；删除模块文件夹即删除整个功能。
2. **自动路由**：全局页在 `src/pages/`（`index.vue` toC 首页、`admin.vue` toB 后台、`setting.vue`、`version.vue`、`404`）；模块页 `src/modules/<模块>/pages/*.vue` → `/<模块>/<页面>`；**入口 `.vue` 不可改名/移位**，拆分只动同模块 `components/`。
3. **组件导入边界**：`src/common/components`、`src/app/components` 自动全局注册，模板直接用；模块组件**显式 import**，不全局注册。
4. **API 统一走公共层**：JSON 用 `src/common/api/http.ts`；流式/Blob 用 `src/common/api/authFetch.ts`；FastAPI 错误解析用 `src/common/api/httpError.ts`；禁止页面自建 fetch/axios。
5. **列表与对话框复用**：分页列表 `useTableQuery`；新增/编辑 `useCrudDialog`；日期格式化 `common/utils/datetime.ts`；禁止页面内重复实现分页/查询/表单重置。
6. **对话框约定**：子组件 `defineExpose({ open })`；每次 `open` 重置表单；`props/emits` 带类型。
7. **菜单与权限**：功能页以后台侧边栏「分组 → 末级子项」平铺，页面内不做页内导航；新页面登记 `src/app/config/menu.ts`，权限码与后端 `config/permissions.py` 一致；菜单过滤用 `useVisibleMenu` / `useVisibleHome`，按钮权限用 `usePermission().hasPerm`。
8. **样式**：默认 UnoCSS 原子类，跨页复用才进 `uno.config.ts`；scoped CSS 仅限白名单（`:deep`、JS 状态激活态、transition、复杂绘制）；颜色只走 `base.css` 的 `--note-*` / `--el-*` 变量，亮暗双模式同时成立。
9. **i18n**：新增词条写到 `src/common/i18n/keys/*.ts`，**禁止多人同改 `language.ts`**。
10. **类型**：`props/emits/接口返回值` 必须有类型，禁止 `any` 兜底；与后端 DO 对齐的类型放模块 `types/`。
11. **依赖**：先 grep 复用，确认无 500MB+ 大库，再同步 `package.json`；新增重库说明分包/惰性加载。

## 3. 典型改动清单

| 改动 | 必做 |
| :--- | :--- |
| 新增模块 | `src/modules/<模块>/{api,components,pages,types}`；`menu.ts` 加菜单；权限码对齐后端 |
| 新增页面 | `pages/` 下建 `.vue`（自动路由）；列表页用 `useTableQuery`；对话框拆 `components/` |
| 新增接口 | 模块 `api/` 封装；统一走 `http.ts`；流式走 `authFetch.ts` |
| 新增按钮权限 | `menu.ts` 声明 `perm`，按钮用 `hasPerm('域:资源:动作')` |
| 新增全局组件 | 放 `common/components/`（自动注册）；业务组件不全局注册 |
| 新增主题色 | `base.css` 建变量 → `uno.config.ts` 注册；同步暗色 |
| 新增词条 | 对应 `i18n/keys/*.ts` |
| 依赖变更 | `package.json` + 分包验证 |

## 4. 验证命令

```bash
cd code/frontend/vue3
pnpm vitest run          # 单元测试
pnpm run build           # 类型检查 + 构建
pnpm run lint            # oxlint + eslint
```

提交前至少保证 `pnpm run build` 通过。
