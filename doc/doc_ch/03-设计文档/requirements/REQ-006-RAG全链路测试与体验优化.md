# REQ-006 RAG 全链路测试与体验优化

> 状态: 已批准(用户 2026-10-18 直接指令)。域: RAG。

## 功能清单

- FEAT-RAGEX-001 会话临时文件上传问答: 知识库对话页可上传临时文件(不入知识库), 解析后作为本轮及后续上下文参与问答; 可与知识库/联网开关自由组合。
- FEAT-RAGEX-002 文件格式白名单与解析引擎对齐: RAG 上传白名单收敛为解析引擎(MinerU)真实支持的格式, 修复"能上传但解析必然失败"的不一致(现状 xlsx/txt/md/csv 等可传不可解)。
- FEAT-RAGEX-003 AG-UI 过程与交互展示打磨: 过程区块(意图/检索/联网)徽章与动效、检索结果统计、引用溯源(知识片段+网络来源)渲染优化、临时文件芯片(实时+历史恢复)。
- 全链路实测: 建库→上传→解析→分块→向量化→检索→问答(多知识库/思考模式/联网开关/临时文件), 流式期间其他异步接口不被阻塞。

## 影响面

- 后端: module_rag(controller/rag_chat.py、do/rag_chat.py、do/conversation.py、do/project_document.py DocType、service/rag_chat.py、service/project_document.py)、module_office(ParserFactory 注册表如需扩图片格式)。
- 前端: modules/rag(pages/conversation.vue、api/conversation.ts、types)、common/components/chat(ChatComposer/ChatMessageList)。
- 不动: config.yaml(基线模板, 用户确认保持现状)。

## 方案要点

- 临时文件: 新端点 `POST /rag/rag-chat/parse-temp-file`(multipart)→ 复用 DocumentParseService.file2markdown(纯文本格式直接解码短路, 版式格式走 MinerU, 全程异步 + CPU 部分 to_thread); 前端附件芯片显示解析状态; 发送时 `ChatRequest.temp_files=[{name, content}]`, 后端以 SystemMessage 注入本 run(checkpointer 持久, 多轮追问可用), 用户消息 blocks 记附件标记供历史恢复。
- 格式对齐: DocType 上传白名单 = ParserFactory 可解析集合(pdf/doc/docx/ppt/pptx + MinerU 实测支持的图片); 文本类(txt/md/csv)仅在临时文件端点做轻量解码, 不回入知识库白名单(尊重"删除 plain 引擎"决策)。
- 非阻塞: 新端点与解析链路全程 async; 扫描修复残留同步 IO/重 CPU 于事件循环上的调用。

## 验收标准

1. 上传白名单内格式→解析→问答全通; 白名单外格式上传被明确拒绝并提示支持格式。
2. 对话页可上传临时文件, 解析状态可见, 问答引用其内容, 追问可延续; 不选知识库也能问答。
3. 知识库多选/清空、深度思考/快速、联网开/关全部可切换且生效。
4. 流式回答期间并行调用其他接口(会话列表/配置等)响应不阻塞。
5. 后端 compileall+冒烟、前端 vue-tsc+build、浏览器全流程验证通过。

## 记录

- 2026-10-18 用户指令立项并批准; 完成。
