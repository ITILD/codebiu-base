# 前端文档导航（vue3）

> 本目录只放**前端实现与前端约束**。文档分层归属、跨层主题矩阵与防冗余规则统一见 [文档总索引](../../../../doc/README.md)（唯一事实来源，本文件不重复定义）。AI 协作规则见 [README_AI.md](../README_AI.md)；后端规则见 [server_py/README_AI.md](../../../backend/server_py/README_AI.md)。

## 前端文档

| 文档 | 内容 | 何时读 |
| :--- | :--- | :--- |
| [01-开发指南](dev/01-开发指南.md) | 目录分层、自动路由、HTTP/流式、列表与对话框复用、新增模块清单 | 开发前 |
| [02-视觉主题规范](dev/02-视觉主题规范.md) | 淡绿自然笔记风、亮暗双模式、UnoCSS 快捷类与颜色令牌 | 做 UI |
| [03-样式写入规范](dev/03-样式写入规范.md) | 样式写在哪、scoped CSS 白名单、全局样式边界 | 写样式 |
| [04-响应式规范](dev/04-响应式规范.md) | 断点体系、移动优先、表格/弹窗/导航自适应 | 做自适应 |
| [05-权限与菜单](dev/05-权限与菜单.md) | menu.ts、路由 meta、按钮权限、首页入口与单页模式 | 接权限 |
| [tag_doc/](tag_doc/version_info.md) | 前端版本时间线与待办 | 发版 / 查变更 |

## 前端入口速查

| 能力 | 文件 |
| :--- | :--- |
| 开发/构建配置、自动路由、分包 | `vite.config.ts` |
| 菜单 / 权限 / 首页入口 | `src/app/config/menu.ts` |
| 菜单权限过滤 | `src/app/composables/useMenu.ts` |
| 权限判断 | `src/common/composables/usePermission.ts` |
| HTTP 封装 | `src/common/api/http.ts` |
| 流式 / Blob 请求 | `src/common/api/authFetch.ts` |
| FastAPI 错误解析 | `src/common/api/httpError.ts` |
| AG-UI 流式事件 | `src/common/api/aguiStream.ts` |
| 分页列表 | `src/common/composables/useTableQuery.ts` |
| 新增/编辑对话框 | `src/common/composables/useCrudDialog.ts` |
| 日期格式化 | `src/common/utils/datetime.ts` |
| 通用表格 | `src/common/components/pro-table/` |
| 后台工作台 / toC 首页 | `src/pages/admin.vue` / `src/pages/index.vue` |

## 常用命令

```bash
cd code/frontend/vue3
pnpm i
pnpm run dev                  # 默认 8888（.env 的 VITE_PORT）
pnpm vitest run               # 单元测试
pnpm run build                # 构建（含 vue-tsc 类型检查）
```
