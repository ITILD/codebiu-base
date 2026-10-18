# 需求卡 REQ-005 网页搜索与 RAG 联网

| 项 | 内容 |
| :--- | :--- |
| 编号 | REQ-005 |
| 名称 | 网页搜索模块与 RAG 联网接入 |
| 状态 | 已交付 |
| 提出人 | 用户（2026-10-18 会话直接下达实现指令，视为对话批准） |
| 批准人 | 用户（同上） |

## 一、功能清单

- FEAT-SEARCH-001 网页搜索独立模块：恢复/移植 module_websearch（duckduckgo/tavily/firecrawl 三引擎，工厂注册表可扩展），暴露 `/websearch/engines`、`/websearch/search` 接口；`websearch` 动态配置组入通用配置页（密钥打码）。
- FEAT-SEARCH-002 RAG 联网检索：知识库问答支持开启网络搜索，网络结果与知识库片段合并为统一候选集，一次 Rerank 精排后分别注入回答上下文与过程区块展示；知识缺口判定兼容"仅有网络结果"场景。

## 二、影响面

- 后端：`module_websearch`（新增）、`module_rag`（do/rag_chat、do/conversation、service/rag_chat、service/project_document_chunk、dao/rag_chat_prompt、utils/llm/stream_classifier）、`common/config/dynamic/schemas.py`、`src/app.py`。
- 前端：`modules/rag/types/index.ts`、`modules/rag/pages/conversation.vue`（联网开关 + 请求参数）。
- 配置：`config.yaml` 已有 `websearch` 种子节（L119-140），首启自动入库；通用配置页新增"网页搜索"组。

## 三、方案要点

- 三级配置分层不变：websearch 组首启以 config.yaml 同名节为种子，之后以 系统管理→通用配置页 为准；`tavily.api_key`/`firecrawl.api_key` 声明为密钥字段（回读打码、缺省保持）。
- 引擎扩展走工厂注册表：`Engine` 枚举 + `SearchEngine` 抽象基类 + `ENGINE_CLASSES` 注册，新引擎三步接入。
- RAG 联网链路（`_knowledge_search_node` 内）：知识库向量粗排（合并场景先不做精排）→ 网络搜索（失败静默不阻断）→ 知识片段 + 网络结果合并统一 doc_list → 用户 Rerank 模型一次精排（`rerank_limit` 截断）→ 拆分回 `knowledge_context_list` 与 `web_results`；`chat` 节点新增 `<网络搜索结果>` 上下文模板。
- 开关优先级：请求级 `ChatRequest.enable_websearch`（显式 true/false）覆盖 → 动态配置 `websearch.rag_enable` 全局默认。
- 跨模块边界：module_rag 仅依赖 module_websearch 的 service 门面（WebSearchService），不直接互引 do/controller。

## 四、验收标准

1. `/websearch/engines` 返回三引擎元信息（默认引擎置顶、可用性正确）；`/websearch/search` 可用配置引擎返回结果。
2. 通用配置页出现"网页搜索"组，密钥打码，修改 default_engine/开关即时生效（TTL 10s）。
3. RAG 会话开启联网后：过程区块展示"网络搜索结果"（标题/来源/相关度），回答引用网络内容；Rerank 模型存在时知识片段与网络结果统一精排（日志可见合并候选数）。
4. 联网开启且知识库零命中但有网络结果时，不触发知识缺口交互。
5. `compileall` 全量通过、`import app` 冒烟通过、核心接口冒烟通过。

## 五、记录

- 2026-10-18 立卡并开发；交付情况见登记册 FEAT-SEARCH-001/002 行。
