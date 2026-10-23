# REQ-013：AI 助手与智能体（Agent）框架

- 域：AGENT　　状态：已交付
- 提出：用户（AI 整理，2026-10-20 修订）　　日期：2026-10-20　　登记册：已加行 ✅
- 一句话：把前端"知识库问答"页升级为"AI 助手"——进入聊天时可选择知识库和/或智能体（Agent）；后台"助手管理"统一管理 Agent 与 Skill；内置 chat（纯读取）与 agent（预留写能力）两个默认 Agent，用户可自建 Agent（配置 skill、默认知识库与默认 prompt）

## 1. 功能清单

| 编号 | 功能 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| FEAT-AGENT-001 | Skill 注册表与内置 Skill（websearch/OCR/文件检索/RAG 问答） | P0 | 已交付 |
| FEAT-AGENT-002 | Agent 执行循环（AG-UI 流式，多轮 skill 调用） | P0 | 已交付 |
| FEAT-AGENT-003 | Agent 模型与配置（默认 prompt/默认知识库/启用 skills） | P0 | 已交付 |
| FEAT-AGENT-005 | 前端 AI 助手页改造（可选知识库和/或 Agent + 我的助手） | P0 | 已交付 |
| FEAT-AGENT-007 | 内置默认双 Agent（chat 纯读取 / agent 预留写能力）与 Skill 能力分级 | P0 | 已交付 |
| FEAT-AGENT-004 | 会话与记忆（agent 会话独立，知识库会话不动） | P1 | 已交付 |
| FEAT-AGENT-006 | 后台助手管理页（Agent 管理 + Skill 清单） | P1 | 已交付 |

## 2. 影响面

- 新增：`module_agent`（五件套：agent CRUD + 对话执行循环 + skill 注册表）；前端 `modules/agent`（管理页、助手选择器、创建对话框组件）
- 修改：前端 rag `conversation.vue` **原位升级**为"AI 助手"（不改文件路径，agent 组件显式 import）；`menu.ts`（toC 入口卡"知识库问答"→"AI 助手"，admin 菜单加"助手管理"）；`app.py`（注册）
- 不改：rag 后端管线与接口、知识库项目管理页
- 数据：新表 `agent_agent`（name/description/default_prompt/default_project_ids/skills/owner_user_id/is_public）；agent 会话新表（独立于 rag 会话，开发时定结构）
- 依赖：无新增（复用 langchain / ag-ui-protocol / 既有模型配置）

## 3. 方案要点

- Skill = 工具的产品化命名：名称/描述/JSON Schema 参数/异步执行函数/**能力级别（只读/写入）**；注册表集中声明，执行循环不感知具体 skill（增删 skill 零改循环）。内置 skill 均为只读级：网页搜索、OCR、文件检索、RAG 知识库问答；用户自定义 skill 仅预留协议本期不做
- 内置默认双 Agent（种子数据，不可删）：**chat** 纯读取（只挂只读 skills：对话/检索/搜索，不修改任何数据）；**agent** 在 chat 基础上预留写入通道，后续支持在**个人权限范围内**（RBAC/数据权限约束下）修改数据——本期只落能力分级框架与入口，不实现写 skill
- Agent 执行循环：LLM 流式 → skill 调用解析 → 执行回填 → 继续生成（可多轮），AG-UI 事件流复用 `aguiStream.ts`，前端渲染 `TOOL_CALL_*` 过程
- 对话对象三模式：**仅知识库**（现有 RAG 管线，行为不变）｜**仅 Agent**（默认 prompt + 默认关联知识库 + 启用 skills）｜**Agent + 知识库**（当前选择覆盖 Agent 默认关联）
- Agent 归属：普通用户可自建私有 Agent（AI 助手页"我的助手"入口，简表单：名称/prompt/默认知识库/skills）；管理员可发布 public（对齐模型配置隔离思路，首期 public/private 两档）
- 后台"助手管理"（命名可议，备选"智能体管理"）：Agent 管理 tab（CRUD + 默认配置）+ Skill 清单 tab（内置只读展示）
- 模型走既有用户级模型配置（public/dept/user 三档位）；不引本地推理与重型 Agent 框架

## 4. 验收标准

- [x] 仅选知识库对话：行为与现状完全一致（回归保障）
- [x] 选启用 websearch 的 Agent 提问 → 工具调用过程前端可视化 → 引用结果回答
- [x] 普通用户在 AI 助手页创建私有 Agent 并可用；后台助手管理页可管理 Agent、查看 Skill 清单
- [x] Agent 的默认 prompt / 默认关联知识库 / 启用 skills 配置在对话中均生效
- [x] AI 助手默认提供 chat 与 agent 两个助手：chat 仅可挂只读 skills、全程不修改数据；agent 预留写级别但本期无写 skill（配置写级 skill 时明确提示未开放）
- [x] 权限点前后端一致；后端 `import app` 无报错；前端 `pnpm run build` 通过

## 5. 记录

- 批准：2026-10-20 用户（"批准全部"，草案 → 已批准）
- 交付：2026-10-22 AI（REQ-013 全部 7 FEAT，状态 → 已交付）

### 交付明细

**后端 module_agent（新模块，五件套齐全）**

- `do/agent.py`：`agent_agent` 表（name/description/default_prompt/default_project_ids JSONB/skills JSONB/owner_user_id/is_public/is_builtin）+ Create/Update/Response 请求响应体
- `skills/registry.py`：Skill 框架——`SkillCapability`（READ/WRITE 能力分级）、`SkillContext`（user_id + default_project_ids 注入）、`SkillDef`（含 JSON Schema 参数模型与异步执行函数）、`SKILLS` 模块级注册表（零常驻开销）；增删 skill 零改执行循环
- `skills/builtin.py`：4 个内置只读 skill——`web_search`（复用 WebSearchService）、`ocr_image`（httpx 下载 15MB 上限 → cv2.imdecode 延迟导入 → OcrService）、`file_search`（复用 FileService.search）、`rag_qa`（复用 ProjectDocumentChunkService.search，project_ids 空则回退 ctx.default_project_ids）
- `service/runner.py`：手工 tool-calling 执行循环（不引 langgraph/checkpointer）——`llm.bind_tools` → `astream` 累积 → reasoning/content 增量 yield → 有 tool_calls 则执行 skill 回填 `ToolMessage` 续跑；`MAX_TOOL_ROUNDS=8` 防失控（末轮强制不挂工具直出）；历史从 chat_message 表重建（最近 20 条，与 rag 图管线 checkpointer 彻底隔离）；助手消息 finally + `asyncio.shield` 防断丢失；复用 `maybe_auto_title`
- `service/agent.py`：AgentService（可见性：公开或本人；CRUD 自建登录即可；内置不可删仅管理员可改）+ `seed_builtin_agents` 幂等种子（`builtin_chat` 无技能 / `builtin_agent` 挂全部只读技能，固定 ID 存在即跳过）
- `controller/agent.py`：9 端点——GET /skills、GET /agents、GET /agents/all（agent:manage:read）、agent CRUD、POST /chat/{conversation_id}/chat（SSE，复用 rag chat 权限点）
- `config/permissions.py`（agent:manage 节点）+ `config/server.py`（`/agent` 子应用挂载 + INIT_HOOKS 播种）
- 会话零新表：复用 conversation 预留 `agent_id` 列与预埋 scope 过滤（all/rag/agent）

**前端**

- `modules/agent/`：types（AgentInfo/SkillInfo/请求体）+ api（CRUD + `sendAgentChatAguiStream` 复用 aguiStream）+ `AgentEditDialog.vue`（创建/编辑复用，skills 多选带描述、选 rag_qa 才显默认知识库多选）+ `pages/manage.vue`（助手列表 + 技能清单双 tab，admin 路由 /agent/manage）
- `modules/rag/pages/conversation.vue` **原位升级**：工具栏加 Agent 选择器（空选项"仅知识库"，agent 模式下知识库/思考/联网/附件禁用）；`scope=agent` 会话列表切换（切回防重入）；会话恢复 agent_id；`startStream` 按 agentId 分流 agent/rag 双链路（rag 链路零改动）；创建会话携带 agent_id；顶栏 agent 标签与空态文案
- `modules/rag/api/conversation.ts`：加 `listAgentConversations`（scope: 'agent'）
- `menu.ts`：toC 入口"知识库问答"→"AI 助手"；admin 加"助手管理"（perm agent:manage）

**验证**

- 新增 `tests/module_agent/test_agent.py` 12 用例全绿：skill 端点/内置种子/401/CRUD 生命周期（非法 skill 400）/内置保护/可见性隔离（他人 agent 404 + 越权改 400）/用户自建/**tool-calling 全链路**（FakeLLM 快照轮次断言：ToolMessage 回填、system 置首、SkillContext.user_id 注入、消息落库、TOOL_CALL 事件带 data）/无工具直答/8 轮上限/未知会话流内 error
- 全量回归 267 passed / 12 failed（267=基线 255+新增 12 精确吻合；12 failed 全为既有存量：rag txt 白名单 7 + office 1 + main 1 + module_ai OCR 环境 2 + Milvus 1，无新增）
- 后端 `import app` 冒烟通过；前端 vitest 16 passed、`build-only` 通过、oxlint 0 错误、type-check 新增代码全净
- 顺手修复 REQ-011 遗留运行时 bug：`NotificationBell.vue` 三处 `res.data.*`（http 封装已解包，导致铃铛永远空）

**包大小与内存约束（用户全局要求）**

- 零新增依赖（复用 langchain_core/ag-ui-protocol/既有模型配置与 websearch/ocr/file/rag 服务）
- 无常驻内存态：SKILLS 为模块级声明注册表；执行循环按请求构建 tools（closure 注入 SkillContext，无全局态）；不引 langgraph/checkpointer（历史走库表重建）
