# flutter — 跨端客户端基线库

Flutter 3.47（Dart 3.13）+ provider + dio + shared_preferences。一套代码同时构建 Android / iOS / Linux / Windows / macOS 客户端，手机与 PC 桌面统一**手机尺寸界面**（桌面窗口 420×880，宽屏内容限宽 460 居中）。

## 快速开始

```bash
cd code/frontend/flutter
flutter pub get
flutter run -d linux        # Linux 桌面（需 clang/cmake/ninja/libgtk-3-dev）
flutter run -d <device-id>  # 连接的手机（adb devices 查看）
flutter build linux --release   # 产物 build/linux/x64/release/bundle/codebiu
flutter build apk --release     # Android 产物 build/app/outputs/flutter-apk/
```

服务器默认地址 `http://localhost:6666`（后端 `server_py` 默认端口）；App 内「设置 → 服务器连接」可修改并测试连通性（手机连本机开发机时改为 `http://<开发机IP>:6666`）。

## 功能范围

- **AI 助手（应用主界面，对话即入口）**：左侧抽屉=会话历史+功能入口；右上角头像菜单=历史/模型/我的/设置/退出；**新建对话时中间展示功能入口卡片（后续新功能默认注册在此）**；在线模式（后端 `/ai/llm/chat` SSE 流式 + 模型选择）与本地模式（离线助手）可切换；会话历史本地持久化
- **知识库**：项目新建/编辑/删除、文档上传（pdf/office/图片）、解析状态轮询、重新解析、删除（后端 `/rag` 接口）
- **智能体配置**：Agent 列表/新建/编辑（提示词+技能选择+公开开关）/删除（后端 `/agent` 接口）
- **认证**：注册（邮箱验证码自适应）、登录（MFA 自适应）、token 自动刷新、登出吊销
- **用户中心**：资料展示/编辑、修改密码、设置（服务器地址、AI 模式、默认模型、明暗主题）

## 目录结构

结构与 Web 端 [vue3/src](../vue3/src) 对齐：**一个后端业务域 = 一个模块**，模块内部再分 `api / types / providers / pages`；跨模块基础设施放 `common/`。会 Vue3 的同学按同名模块即可找到对应代码。

```text
lib/
├── main.dart                    # 入口：初始化 AppCore（设置/会话/Dio）
├── app.dart                     # MaterialApp + 主题 + PhoneShell（宽屏限宽）
├── common/                      # 跨模块基础设施（不含业务页面）
│   ├── app_core.dart            # 服务定位器/组合根：dio/settings/session/各模块 api
│   ├── constants.dart           # 常量（默认服务器地址、限宽）
│   ├── settings.dart            # AppSettings：地址/AI模式/模型/主题（持久化）
│   ├── theme.dart               # 自然笔记主题（明暗）+ PhoneShell
│   └── services/                # 跨模块共用能力
│       ├── api_error.dart       # 错误中文化
│       ├── auth_interceptor.dart# Bearer 注入 + 401 刷新重放
│       └── local_assistant.dart # 离线本地助手
└── modules/                     # 业务模块（与 vue3/src/modules 同名）
    ├── authorization/           # 认证与用户中心
    │   ├── api/auth_service.dart
    │   ├── session.dart         # 令牌与当前用户存储
    │   ├── types/               # auth.dart / user.dart
    │   ├── providers/auth_provider.dart
    │   └── pages/               # login / register / password / profile / profile_edit
    ├── ai/                      # AI 对话
    │   ├── api/ai_service.dart
    │   ├── types/               # chat_message / conversation / model_config
    │   ├── providers/chat_provider.dart
    │   └── pages/               # chat_page / model_picker_page
    ├── agent/                   # 智能体
    │   ├── api/agent_service.dart
    │   ├── providers/agent_provider.dart
    │   └── pages/agent_page.dart
    ├── rag/                     # 知识库
    │   ├── api/rag_service.dart
    │   ├── types/kb_project.dart
    │   ├── providers/rag_provider.dart
    │   └── pages/               # knowledge_page / kb_project_page
    └── main/                    # 应用级页面
        └── pages/               # auth_gate / settings_page
```

### 与 Vue3 的对应关系

| Vue3（`vue3/src`） | Flutter（`flutter/lib`） | 说明 |
| :--- | :--- | :--- |
| `modules/<模块>/api/` | `modules/<模块>/api/` | 一个后端域一个客户端类（`xxx_service.dart`） |
| `modules/<模块>/types/` | `modules/<模块>/types/` | 数据类型定义（Dart 类 + `fromJson`/`toJson`） |
| `modules/<模块>/pages/` | `modules/<模块>/pages/` | 页面（`xxx_page.dart`） |
| `modules/<模块>/stores/`（Pinia） | `modules/<模块>/providers/` | 状态与动作（ChangeNotifier，需注册到 `MultiProvider`） |
| `modules/<模块>/components/` | `modules/<模块>/components/` | 模块内组件；当前无独立组件，后续按需新建 |
| `modules/<模块>/styles/` | — | 统一由 `common/theme.dart` 提供主题与样式 |
| `modules/<模块>/utils/` | — | 通用能力放 `common/services/` |
| `common/` | `common/` | 跨模块共用（Api 请求封装、错误、主题、设置） |

后端模块对应：`authorization`↔`src/module_authorization`、`ai`↔`src/module_ai`、`agent`↔`src/module_agent`、`rag`↔`src/module_rag`、`main` 为客户端自身的壳（登录门与设置）。

> 只创建有代码的模块，不建空目录；Flutter 端暂无 contact/file/task 等模块的界面。

## 项目文档

- [客户端文档导航](./doc/README.md)（含开发指南、代码规范、新成员与 AI 协作指南）
- [AI 协作规则](./README_AI.md)
- [版本信息](./doc/tag_doc/version_info.md)
