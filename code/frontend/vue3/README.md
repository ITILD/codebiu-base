# vue3 — 前端基线库

Vue 3.5 + TypeScript + Vite + Element Plus + UnoCSS + Pinia + unplugin 全家桶（自动路由 / 自动导入 / 图标）。

## 快速开始

```bash
cd code/frontend/vue3
pnpm i
pnpm run dev        # http://localhost:8888（端口取 .env 的 VITE_PORT）
pnpm run build      # vue-tsc 类型检查 + 生产构建
pnpm vitest run     # 单元测试
```

## 目录结构

```text
src/
├── common/             # 跨业务公共层：api / components / composables / enums / i18n / stores / types / utils
├── app/                # 应用壳：layout 与设置面板组件 / composables(config) / menu.ts
├── modules/<模块>/     # 业务垂直切片：api / components / pages / types
└── pages/              # 全局页：index.vue(toC) / admin.vue(toB) / setting / version / 404
```

## 项目文档

- [前端文档导航](./doc/README.md)（含开发指南、视觉主题、样式、响应式、权限与菜单）
- [AI 协作规则](./README_AI.md)
- [版本信息](./doc/tag_doc/version_info.md)
