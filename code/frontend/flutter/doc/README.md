# 客户端文档导航（flutter）

> 本目录只放**Flutter 客户端实现与客户端约束**；跨端需求、总体架构、权限模型、开发治理规范在根目录 [doc/](../../../../doc/README.md)。AI 协作规则见 [README_AI.md](../README_AI.md)；后端规则见 [server_py/README_AI.md](../../../backend/server_py/README_AI.md)；Web 前端规则见 [vue3/README_AI.md](../../vue3/README_AI.md)。

## 文档分层

| 层 | 位置 | 内容 |
| :--- | :--- | :--- |
| 项目级 | [doc/](../../../../doc/README.md) | 需求登记册、需求分析、总体架构、权限设计、跨端规范 |
| 客户端级 | 本目录 | 开发部署、目录结构、分层方案、代码规范、新成员与 AI 指南、版本记录 |
| 运维级 | [deveops/](../../../../deveops/README.md) | 服务端构建、Docker 部署、发布与升级 |

## 客户端文档

| 文档 | 内容 | 何时读 |
| :--- | :--- | :--- |
| [01-开发指南](dev/01-开发指南.md) | 环境搭建、开发部署、目录结构、分层方案、后端对接、新增页面清单 | 开发前 |
| [02-代码规范](dev/02-代码规范.md) | Dart/Widget 命名、状态管理、异步与错误处理、样式与主题硬规则 | 写代码 |
| [03-新成员与AI协作指南](dev/03-新成员与AI协作指南.md) | 新员工上手路径、AI 辅助开发的任务拆解与验收、典型改动 SOP | 入职 / 用 AI 开发时 |
| [tag_doc/](tag_doc/version_info.md) | 客户端版本时间线与待办 | 发版 / 查变更 |

## 代码入口速查

> 目录与 [vue3/src](../../vue3/src) 对齐：业务代码在 `lib/modules/<模块>/`（`api / types / providers / pages`），跨模块基础设施在 `lib/common/`。模块名与后端 `src/module_*` 同名。

| 能力 | 文件 |
| :--- | :--- |
| 服务定位器（Dio/设置/会话/业务服务） | `lib/common/app_core.dart` |
| 服务器地址 / AI 模式 / 主题持久化 | `lib/common/settings.dart` |
| 常量（默认地址/限宽） | `lib/common/constants.dart` |
| 登录会话与令牌存储 | `lib/modules/authorization/session.dart` |
| 认证拦截（Bearer 注入 + 401 刷新重放） | `lib/common/services/auth_interceptor.dart` |
| 登录/注册/资料/密码 API | `lib/modules/authorization/api/auth_service.dart` |
| 认证/用户状态 | `lib/modules/authorization/providers/auth_provider.dart` |
| 用户资料模型 | `lib/modules/authorization/types/user.dart` |
| 认证响应模型 | `lib/modules/authorization/types/auth.dart` |
| 对话 API（SSE 流式 + 非流式回退） | `lib/modules/ai/api/ai_service.dart` |
| 模型列表 API | `lib/modules/ai/api/ai_service.dart`（`chatModels`） |
| 对话状态与动作 | `lib/modules/ai/providers/chat_provider.dart` |
| 对话数据类型 | `lib/modules/ai/types/`（`chat_message` / `conversation` / `model_config`） |
| 离线本地助手 | `lib/common/services/local_assistant.dart` |
| 错误信息中文化 | `lib/common/services/api_error.dart` |
| 知识库状态 / API / 类型 | `lib/modules/rag/providers/rag_provider.dart` · `api/rag_service.dart` · `types/kb_project.dart` |
| 智能体状态 / API | `lib/modules/agent/providers/agent_provider.dart` · `api/agent_service.dart` |
| 主题（自然笔记色系 + 明暗） | `lib/common/theme.dart` |
| 宽屏手机壳（限宽 460） | `lib/common/theme.dart`（`PhoneShell`） |
| 页面 | 对话 `modules/ai/pages/chat_page.dart`（抽屉+头像菜单+**新功能入口卡片**）· 知识库 `modules/rag/pages/` · 智能体 `modules/agent/pages/agent_page.dart` · 登录/注册/资料/密码 `modules/authorization/pages/` · 模型选择 `modules/ai/pages/model_picker_page.dart` · 登录门/设置 `modules/main/pages/` |
| 桌面窗口尺寸（420×880） | `linux/runner/my_application.cc` · `windows/runner/main.cpp` · `macos/Runner/MainFlutterWindow.swift` |
| Android 明文传输与网络权限 | `android/app/src/main/AndroidManifest.xml` |
| iOS 允许 HTTP 后端 | `ios/Runner/Info.plist`（NSAppTransportSecurity） |
