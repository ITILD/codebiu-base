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

```text
lib/
├── main.dart               # 入口：初始化 AppCore（设置/会话/Dio）
├── app.dart                # MaterialApp + 主题 + PhoneShell（宽屏限宽）
├── core/                   # 与 UI 无关的核心层
│   ├── app_core.dart       # 服务定位器：dio/settings/session/auth/ai
│   ├── constants.dart      # 常量（默认服务器地址、限宽）
│   ├── settings.dart       # AppSettings：地址/AI模式/模型/主题（持久化）
│   ├── session.dart        # 会话存储：access/refresh 令牌 + 用户
│   ├── models/             # 数据模型：User/Auth/ModelConfig/ChatMessage/Conversation/KbProject
│   └── services/           # API 客户端：auth/ai/rag/agent + 拦截器/错误/本地助手
├── providers/              # ChangeNotifier 状态层：Auth/Chat/Rag/Agent
└── ui/                     # 界面层
    ├── theme.dart          # 自然笔记主题（青绿主色 + 明暗，与 Web 端 --note-* 令牌同源）
    └── pages/              # 页面：对话主页(抽屉+头像菜单)/知识库/文档/智能体/登录/注册/模型选择/资料/密码/设置
```

## 项目文档

- [客户端文档导航](./doc/README.md)（含开发指南、代码规范、新成员与 AI 协作指南）
- [AI 协作规则](./README_AI.md)
- [版本信息](./doc/tag_doc/version_info.md)
