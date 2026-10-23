"""智能体模块(REQ-013): AI 助手与智能体框架

- skills/         Skill 注册表(只读内置: 联网搜索/图片OCR/文件检索/知识库问答)
- service/agent   助手 CRUD + 可见性(公开或自建) + 内置双 Agent 种子
- service/runner  手工 tool-calling 执行循环(bind_tools→astream→执行→回填)
- controller      /agent/agents* CRUD, /agent/skills 清单, /agent/chat/{cid}/chat SSE
对话复用 rag 会话表(conversation.agent_id)与 AG-UI 协议链路, 零新增依赖。
"""
