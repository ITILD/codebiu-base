# REQ-018：AI 能力平台架构（Model / Skill / Agent 三层一等公民）
- 域：AICAP　　状态：批次 1/2/3 已交付（全部三期落地：契约层/SkillRuntime/双 Skill 样板/kb_ingest_agent/三入口 → 队列拆分/附件链路/prompt Skill/断点续跑 → script 沙箱/Skill Hub/MCP adapter/计费口径；ai_agent 的 plan_execute 后置待单独立项）
- 提出：用户　　日期：2026-11-11　　登记册：已加行 ✅
- 一句话：把平台主要能力抽象为 Model（能力供给：ai_model + static_func）/ Skill（单一技能）/ Agent（一整套任务的工作流或角色）三层一等公民，抽象与能力逐级增大、每层均有 ai/static 双形态；问答自动调用、页面手动触发、Celery 排队三条入口共用一个 SkillRuntime。

## 1. 功能清单

| 编号 | 功能 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| FEAT-AICAP-001 | 三层契约：Skill Manifest（nature/execution/idempotency）+ Model 能力注册（ai_model + static_func） | P0 | 批次 1 已交付 |
| FEAT-AICAP-002 | SkillRuntime 统一调用（auto 模式选择 inline/queued）+ skill_invocation 观测 + agent_job_run（Agent 级观测/幂等/断点载体） | P0 | 批次 1 已交付 |
| FEAT-AICAP-003 | `doc_parse` Skill（markdown + 结构块双产物，hybrid，OCR 可降级） | P0 | 批次 1 已交付 |
| FEAT-AICAP-004 | `doc_chunk_index` Skill（规则/语义分块 + 向量化入库，hybrid） | P0 | 批次 1 已交付 |
| FEAT-AICAP-005 | `kb_ingest_agent`（static_agent，LangGraph 固定工作流 parse→index + fan_out） | P0 | 批次 1 已交付 |
| FEAT-AICAP-006 | 三条触发路径贯通：Agent Tool Adapter（问答自动）/ Web Controller（手动）/ Task Executor（Celery） | P0 | 批次 1 已交付 |
| FEAT-AICAP-007 | 既有 4 只读技能（web_search/ocr/file_search/kb_qa）Manifest 化迁移 | P1 | 批次 1 已交付 |
| FEAT-AICAP-008 | 会话附件高优先级链路 + q_interactive 独立 worker + 物理队列拆分与 resource_domain 准入配额（批次 2） | P1 | 批次 2 已交付 |
| FEAT-AICAP-009 | prompt 自定义 Skill（批次 2）；批次 3：script 沙箱 Skill（bash/node 泛化）+ Skill Hub（社区 SKILL.md 包加载器 + MCP adapter，W-14/W-15） | P2 | 批次 2/3 已交付（ai_agent plan_execute 后置） |
| FEAT-AICAP-010 | 批处理条件编排：steps 线性 + fan_out + depends_on + 批内条件 when/skip_if（降级产物不自动入库） | P0 | 批次 1 已交付 |

## 2. 影响面

- 后端：`module_agent`（SkillRuntime/Agent 两形态/观测表，主改造）、`module_ai`（+static_func 能力注册）、`module_rag`/`module_office`（skills/ 目录宿主，`reparse_document_task` 拆解）、`module_task`（队列语义 priority_class/resource_domain）、`module_authorization`（新权限项）
- 前端：vue3 智能体中心升级为能力中心三页（模型能力/技能管理/智能体）；flutter 客户端 agent 配置语义对齐（agent_callable）
- 数据：新表 `ai_skill`/`ai_skill_version`/`skill_invocation`，扩展 `ai_agent`（agent_kind/decision_mode/steps）、`task_queue`（+invocation_id）；Alembic 增量脚本
- 依赖：零新增（LangGraph/LangChain/Celery 既有白名单内）

## 3. 方案要点

- 三层抽象与能力逐级增大：Model（ai_model 大小模型 + static_func 固定规则函数）→ Skill（ai_skill/static_skill/hybrid 单一技能）→ Agent（ai_agent ReAct / static_agent 固定工作流 / hybrid 编排）
- 单向依赖 `Agent → Skill → Model(可选) → Service`；组合只在 Agent 层；static 能力零模型必须可运行
- 三条入口（页面 Controller / 对话 Tool Adapter / Celery Executor）汇合于同一 SkillRuntime，同一 Skill 一份实现两种外壳（inline/queued）
- 首个样板即需求举例：doc_parse（双产物）+ doc_chunk_index 两 Skill 由 kb_ingest_agent 编排；问答上传文件自动入库、知识库页手动触发、推 Celery 三路行为一致
- v1.1 评审定案（2026-11-11，逐条见 04 文档 §11）：禁止 Agent 调用 Agent（无过渡形态）；降级分流在编排层 when/skip_if 表达；agent_job_run 设计内建不后置；队列机制/语义一步到位不做 v1/v2 分叉；API 契约一步到位（vue3/flutter 同交付适配）；「分期只是交付顺序，不是语义分期」
- 外部生态接入增补（04 文档 §3.5，W-14/W-15）：社区 SKILL.md 渐进式包与 MCP server tools **不新增第四层、不绕过 SkillRuntime**——SKILL.md 包由 Skill Hub 加载器拆解（指令→prompt Skill、脚本→script 沙箱 Skill、references→知识资产，命名空间 `pack.{包名}`）；MCP tools 由 adapter 反射注册（JSON Schema→input_schema，命名空间 `mcp.{server}`）；skill_type 全枚举一步定义：builtin_tool/prompt/python_script/script/mcp_tool
- 设计权威文档：[04-AI能力平台架构设计](../04-AI能力平台架构设计.md)（TL;DR/判定树/契约/队列/数据模型/分期/评审定案全量）

## 4. 验收标准

### 批次 1（已验收 2026-11-11）

- [x] 三条路径触发同一文档入库，行为一致且全部可在 skill_invocation 追溯（批次 1：Controller `/ingest`、对话 Tool Adapter、Celery `skill_execute`/`reparse_document_task`→kb_ingest 均汇合 SkillRuntime；`/agent/invocations` 可查）
- [x] 零模型配置环境：static_func / static_skill / rule Agent 全链路可运行（CA-06；单测打桩零能力环境验证降级与 BM25-only 路线）
- [x] hybrid Skill（doc_parse）OCR 缺失时降级成功并标记 degraded；核心文本缺失直接失败；降级产物被编排层 skip_if 拦截、不自动入库（W-2；test_agent_job.test_degraded_parse_skipped_from_index）
- [x] agent_job_run 可查：job 提交/步骤状态（含 when/skip_if 判定结果）/进度/断点续跑（W-3；steps_state 落库 + `/agent/job-runs/{id}`；断点续跑全链路批次 2，载体内建）
- [x] 既有问答、知识库上传/重解析、4 个只读技能回归通过（全量回归 410 过；4 个存量配置分层环境失败经 stash 对照确认与本次无关）
- [x] `ai_skill:invoke` 仅管理员/调试台可用；Skill 越权资源访问被拦截（CA-08；普通用户 invoke 403 + doc_chunk_index project_ids 归属校验）

### 批次 2（已验收 2026-11-11）

- [x] q_interactive 物理队列：priority≥7 自动路由交互队列，批量任务积压不影响会话交互（单测验证路由；WORKER_QUEUES 支持独立 worker 部署形态）
- [x] 会话附件解析走 SkillRuntime（interactive 优先级 + inline 硬超时），附件解析入 skill_invocation 可追溯
- [x] prompt 自定义 Skill：draft→published→deprecated 状态机、发布注册/下线反注册、模板变更版本快照自增、进程重启从 DB 恢复注册、经 SkillRuntime 三入口一致调用
- [x] 断点续跑全链路：job 图接 PostgreSQL checkpointer（W-12）、步骤产物入 checkpoint（consume 跨进程可续）、item 级断点（已成功项复用不重复执行）、`POST /agent/job-runs/{id}/resume`
- [x] vue3 能力中心（技能管理+调试台+自定义 Skill+调用记录+job 页签/模型能力页/文档入库入口）与 flutter agent 页（全局键/nature 徽标/agent_callable 过滤）契约对齐

### 批次 3（已验收 2026-11-12）

- [x] 沙箱逃逸测试通过（env 白名单外清空/超时杀进程/非零退出报 permanent/附加文件路径穿越拦截；进程级强隔离依赖部署层容器化，边界已文档化）
- [x] 社区包/MCP tools 注册后可在对话中调用且 skill_invocation 可追溯（pack.* 拆解注册+沙箱执行、mcp.* 反射注册+短连接调用，单测端到端验证含恢复与删除）
- [x] 计费口径 = skill_invocation + agent_job_run 双粒度（`GET /agent/usage/summary` 按 Skill 聚合调用量/成功率/降级/tokens/时长 + 按 job 聚合运行量）
