# flutter 客户端版本信息

> 发版/变更记录按时间倒序追加；不改写历史条目。

## 未发布（2026-11-11）

**契约对齐：AI 能力平台（REQ-018，flutter 端最小适配）**
- `/agent/skills` 适配新响应（Manifest 视图）：技能多选 value 改用全局键 `key`（如 `sys.web_search`）、label 用展示名 `name`；存量旧短名（不含 "."）已保存值在编辑回显时原样展示、可移除（后端兼容解析，不报错）
- 技能选择项展示 nature 徽标（static=规则 / ai=模型 / hybrid=混合）；`agent_callable=false`（不可对话调用）的技能在选择器中禁用
- `/agent/agents` 新增字段解析：`agent_kind`（chat/job，job 类显示「任务」徽标，不做 job 管理）与 `decision_mode`（rule/model/hybrid）；列表技能副标题按键回显展示名
- 新增 `test/agent_model_test.dart`（模型 fromJson 单测）

**验证**：`flutter analyze` 0 issue、`flutter test` 全过、分层越界检查无输出

## 未发布（2026-11-08）

**重构：目录结构向 Vue3 对齐**
- `lib/` 调整为 `common/` + `modules/<模块>/{api,types,providers,pages}`；模块名与 `vue3/src/modules/*`、后端 `src/module_*` 同名（`authorization` / `ai` / `agent` / `rag` / `main`）
- 原 `core/`、`ui/`、`providers/` 按业务域拆入对应模块；主题、设置、常量、拦截器、错误中文化、AppCore 组合根归入 `common/`
- 仅调整路径与相对 import，功能与界面不变；README、README_AI、doc/dev 01~03、REQ-017 文档同步更新

**验证**：当前开发机未安装 Flutter SDK，未执行 `flutter analyze` / `flutter test`；已用脚本校验全部 144 条 import 路径可解析

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
