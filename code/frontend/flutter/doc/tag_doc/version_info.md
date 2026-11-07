# flutter 客户端版本信息

> 发版/变更记录按时间倒序追加；不改写历史条目。

## 0.2.0（2026-11-07）

**重构：对话即入口（基线形态）**
- 去掉底部导航：AI 对话页成为唯一主界面；「我的」等入口迁移到右上角**头像菜单**（历史记录/选择模型/我的/设置/退出登录）
- 左侧抽屉（左滑呼出）：会话历史列表（切换/删除）、新建对话、智能体配置、知识库入口
- 会话历史本地持久化（SharedPreferences，上限 50 条 / 每条 200 消息，首条消息自动成标题）
- **新建对话时中间展示功能入口卡片**（知识库第一个入驻；后续所有新功能默认入口注册在 `chat_page.dart _EmptyView._features`）

**新增：知识库管理**
- 项目：列表/新建（名称/描述/个人-项目-公司分类/私有开关）/编辑/删除（`/rag/projects`）
- 文档：file_picker 选择上传（pdf/doc/docx/ppt/pptx/png/jpg/jpeg）、解析状态轮询（3s）、重新解析、删除（`/rag/project-documents`）

**新增：智能体配置**
- Agent 列表（内置标识）、新建/编辑（提示词+技能多选+公开开关）、删除（`/agent/agents`、`/agent/skills`）

**依赖**：新增 `file_picker ^13.3.2`（系统文件选择；Android 需 minSdk 23 / compileSdk 36，已配置）

**验证**：analyze 0 issue、单测通过、Linux release 构建、APK 重建；RAG/Agent 接口与后端实测对齐（64 项目、4 技能、2 内置智能体）

## 0.1.1（2026-11-07）

**视觉**
- 图标统一：iOS/macOS/Android/Windows 全部替换为 Web 端飞鱼图标（`vue3/public/favicon.svg` 渲染），移除 Flutter 模板默认图标
- 色系向 Web 端「自然笔记」风格靠拢：亮色主色 #2E7C6B / 纸面 #EFF3F1 / 描边 #D8E1DD；暗色主色 #38A487 / 纸面 #0D1319 / 卡片 #1A232C（对应 vue3 `--note-*` 令牌）；保留手机端紧凑布局与聊天气泡等移动特色

**交互**
- 输入框支持回车发送：桌面 Enter 发送、Shift+Enter 换行；手机软键盘显示「发送」动作键；发送中回车不再误清空输入

**验证**：analyze 0 issue；Linux release 构建并冒烟运行正常；Android debug APK 重建通过

## 0.1.0（2026-11-07）

初版：手机与 PC 桌面同构客户端。

**功能**
- 认证：注册（邮箱验证码流程按 register-config 显隐）、登录（MFA 显隐）、令牌自动刷新与登出吊销
- 用户中心：信息展示、资料编辑、修改密码、退出登录
- AI 助手：在线模式（/ai/llm/chat SSE 流式 + /ai/model-configs 模型选择，失败回退非流式）；本地模式（离线助手：计算/时间日期/闲聊，打字机效果）
- 设置：服务器地址（保存并测试）、在线/本地切换、默认模型、明暗主题
- 跨端：Android/iOS/Linux/Windows/macOS 五平台壳；桌面窗口 420×880；宽屏 PhoneShell 限宽 460

**工程**
- Flutter 3.47.9 / Dart 3.13；依赖 dio + provider + shared_preferences
- 分层：ui → providers → core/services → core/models；README_AI 硬规则与文档体系（doc/dev 01~03）
- 验证：analyze 0 issue、单测通过、Linux release 构建通过、后端全链路联调通过

**待办**
- 会话历史持久化（当前仅内存）
- 消息复制以外的批量操作（多选删除/导出）
- 桌面端多窗口/系统托盘评估
- CI：GitHub Actions 跑 analyze+test+build
