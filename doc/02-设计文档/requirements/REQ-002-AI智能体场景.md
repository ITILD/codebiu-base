# REQ-002：AI 智能体场景（场景化组合 · 产物交付 · 运营收口）
- 域：AGENT　　状态：已批准
- 提出：用户　　日期：2026-11-17　　登记册：已开卡 ✅
- 一句话：给平台终端用户，把 REQ-018 三层架构与 REQ-019 执行协议组合成**开箱即用的智能体场景**——深度研究、批量文档处理、办公创作三个内置场景 Agent，统一「产物落虚拟文件系统 + 验收模板 + 场景入口」底座；同时收口两项平台遗留（`agent.*` 协议事件前端消费与任务清单视图、北极星看板），human 验收审批闭环作为可选尾批。

> 详细设计：[06-AI智能体场景设计](../06-AI智能体场景设计.md)（v1.0）
> 上游架构：[04-AI能力平台架构设计](../04-AI能力平台架构设计.md)（v1.2）、[05-对话智能体与执行协议设计](../05-对话智能体与执行协议设计.md)（v1.0）
> 前置依赖：REQ-018 批次 1/2/3、REQ-019 批次 4/5（均已交付）

## 1. 功能清单

| 编号 | 功能 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| FEAT-AGENT-008 | 会话任务清单视图：`agent.plan_update` / `agent.verdict` / `agent.skill_masked` 前端消费 + 清单折叠块实时渲染 + `GET /agent/plans/{run_id}` 断线兜底与历史回放 | P0 | 草案 |
| FEAT-AGENT-009 | 北极星看板：假完成率 / 任务成功率 / 每成功任务成本聚合端点 + toB 运营页（含失败原因与预算触底下钻） | P0 | 草案 |
| FEAT-AGENT-010 | 场景底座：产物 VFS 归档（workspace → `/agent_runs/{run_id}/`，事件携带 `file_id` 可预览下载）+ 验收模板库 + 场景入口（flutter 空态功能卡片 / vue3 场景快捷选择） | P0 | 草案 |
| FEAT-AGENT-011 | 深度研究 Agent（`research_agent`，plan_execute）：检索计划 → 多源证据 → 引用编号报告 `report.md`，artifact 验收（章节数 / 引用数 / 字数下限） | P0 | 草案 |
| FEAT-AGENT-012 | 批量文档处理 Agent（`batch_docs_agent`，plan_execute）：会话多附件逐文档「解析 → 转换 / 摘要 → 产物」，cmd + artifact 验收，产物打包归档 | P1 | 草案 |
| FEAT-AGENT-013 | 办公创作 Agent（`office_agent`，react）：一句话生成 docx / xlsx / pptx（Skill Hub 官方包），产物自动落 VFS + 自动结构校验（react 场景的轻量验收降级） | P1 | 草案 |
| FEAT-AGENT-014 | human 验收审批闭环：挂起-审批-续跑（不阻塞进程等待）+ 通知中心触达 + 会话内审批卡片 + toB 审批入口 + 超时视为未通过 | P2（可选） | 草案 |

## 2. 影响面

- 新增：
  - `code/backend/server_py/src/module_agent/agents/scenarios.py`（三个场景 Agent Manifest，代码为事实源）
  - `module_agent/service/artifact_archive.py`（产物 VFS 归档）
  - `module_agent/service/acceptance_templates.py`（验收模板库）
  - `module_agent/api/metrics.py`（北极星聚合端点）
  - 前端 `modules/chat` 任务清单折叠块组件（vue3）与 flutter 清单渲染；`modules/agent` 运营看板页签（toB）
- 修改：
  - `module_agent/service/runner.py`（plan_execute 收尾产物归档；事件 payload 附 `file_id`）
  - `module_agent/service/agent_planner.py`（human 挂起-续跑；验收模板注入，批次 8）
  - `module_ai/utils/llm/stream/agui.py`（如需补充 `agent.human_review` 事件，批次 8）
  - 前端 `common/types/agui.ts`（`AGUI_CUSTOM_NAME` 补 `agent.plan_update` / `agent.verdict` / `agent.skill_masked`）、`common/composables/useAguiMessages.ts`（清单块聚合）、`modules/chat`（场景快捷选择）
  - flutter：聊天页空态功能卡片（场景入口）、清单折叠块
- 数据：`agent_plan_item` 增 `artifact_files`（JSON，产物 `[{file_id, name}]`）；无新表；Alembic 增量脚本
- 依赖：无新第三方库
- 顺带（豁免类，不占 FEAT）：删除 `deep_thinking` 兼容字段（05 §2.3 到期）

## 3. 方案要点

- 场景 = **内置 Agent Manifest + Skill 组合 + 验收模板 + 前端入口**，全部走既有三层与五拍协议，不新增执行机制：
  - `research_agent`（ai_agent / plan_execute）：`web_search` + `kb_search`（命中知识库时）+ Skill 句柄；产物 `report.md` 带编号引用；
  - `batch_docs_agent`（ai_agent / plan_execute）：`doc_parse` + Skill Hub `pack.docx/pptx/xlsx` + `run_script`；逐文档一项，产物逐项验收后打包；
  - `office_agent`（ai_agent / react）：对话式生成，产物自动落 VFS + 自动结构校验（**场景选策略**：单文件创作是对话任务，不上五拍清单）。
- 产物归档：`submit.artifacts` 在 verdict 通过后上传 VFS `/agent_runs/{run_id}/`，`agent_plan_item.artifact_files` 记 `file_id`，前端 verdict 卡片可预览 / 下载（复用 REQ-016 预览）。
- 验收模板：模板是**建议不是强制**（模型可加强不可削弱，`acceptance_hash` 机制不变）；write_plan 注入场景模板目录供模型选用。
- 北极星看板：`GET /agent/metrics/north-star`（管理员），指标口径 = 05 §4.9 三项，来源 `agent_plan_item` + `skill_invocation`（by `agent_run_id`）；其余指标仅下钻用。
- human 闭环：human 项到达时 run 以 `awaiting_human` 优雅收尾（不进程内等待），审批（或超时默认未通过）后 API 触发**续跑**（已完成项跳过）。
- 关键约束（不变量）：场景 Agent 不得绕过五拍协议自造完成判定；产物必须落 VFS 才算可交付；react 场景无闸门但必须有自动结构校验；禁止 Agent 调 Agent、Skill 不互相编排（沿用 04/05）。

## 4. 验收标准

### 批次 6（平台收口：清单视图 + 北极星）✅ 已交付 2026-11-18

- [x] 会话内实时出现任务清单折叠块：write_plan 全量渲染，verdict 后对应项状态与原因即时更新，skill_masked 有提示
- [x] 刷新 / 历史会话打开时清单可从 `GET /agent/plans/{run_id}`（或消息 process_blocks）恢复，与实时态一致
- [x] 北极星三项（假完成率 / 任务成功率 / 每成功任务成本）按时间窗与 Agent 维度可查，数字与 `agent_plan_item` 明细可对账
- [x] `deep_thinking` 字段删除后，旧客户端请求不报错（`mode` 通道不受影响），回归通过

### 批次 7（场景底座 + 深度研究）

- [ ] `research_agent` 会话给定研究主题：清单含检索与写作分项，报告产物含编号引用与来源列表
- [ ] artifact 验收拦截不达标报告（章节数 / 引用数 / 字数任一不足即未通过），两败改单生效
- [ ] 验收通过的产物出现在 VFS `/agent_runs/{run_id}/`，前端 verdict 卡片可预览 / 下载
- [ ] flutter 空态功能卡片与 vue3 场景快捷选择可进入三个场景会话（未交付场景置灰）
- [ ] 无联网且无知识库时 research 场景给出明确前置提示（不空跑预算）

### 批次 8（批量文档 + 办公创作 + human 闭环）

- [ ] `batch_docs_agent` 对会话多附件逐文档产出转换 / 摘要文件，全部验收通过后打包归档，含逐项明细
- [ ] `office_agent` 对话生成 docx / xlsx / pptx 至少各一例，产物自动落 VFS 且结构校验失败会自动重试一次并提示
- [ ] human 项：run 挂起后站内信触达，会话卡片与 toB 入口均可批；批准后续跑跳过已完成项，拒绝 / 超时（默认 24h）按未通过进入两败改单
- [ ] 后端 `import app` 无报错；前端 `pnpm run build` 通过；`module_agent` / `module_rag` / `module_ai` 既有测试全绿

## 5. 记录

- 批准：2026-11-18 用户批准设计 v1.0，从批次 6 开始实施（草案 → 已批准）
- 交付：<待填写>，v1.0（验收标准已全勾）（已批准 → 已交付）
