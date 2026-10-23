"""module_agent 智能体测试(REQ-013): 技能注册表/CRUD 可见性/内置保护/tool-calling 循环

LLM 以 FakeLLM 打桩(两轮: 工具调用→最终答案), 内置技能 func 以桩替换,
测试自建会话/Agent 测完自清理, 零外部依赖。
"""

import uuid

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from module_agent.do.agent import AgentCreate, AgentUpdate
from module_agent.dao.agent import AgentDao
from module_agent.skills.registry import SKILLS
from module_agent.service.agent import BUILTIN_AGENT_ID, BUILTIN_CHAT_ID
from module_rag.dao.conversation import ConversationDao
from module_rag.do.conversation import ConversationCreate
from module_rag.service.chat_message import ChatMessageService
from module_rag.service.conversation import ConversationService
from module_rag.service.user_model import ResolvedModel, UserModelService


# ################ 测试桩 ################


class _FakeBind:
    """bind_tools 返回的 Runnable 桩: 逐轮弹出预置 chunk 序列"""

    def __init__(self, llm: "_FakeLLM"):
        self._llm = llm

    async def astream(self, messages):
        self._llm.snapshots.append(list(messages))
        for chunk in self._llm.rounds.pop(0):
            yield chunk


class _FakeLLM:
    """LLM 桩: rounds 每项是一轮 chunk 列表; 无工具路径直接吐最终答案"""

    def __init__(self, rounds=None):
        self.rounds = list(rounds or [])
        self.direct_answer: list = []  # 无工具路径(llm.astream)输出的 chunk
        self.snapshots: list = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return _FakeBind(self)

    async def astream(self, messages):
        self.snapshots.append(list(messages))
        for chunk in self.direct_answer:
            yield chunk


def _tool_call_chunk(name: str, args_json: str, call_id: str) -> AIMessageChunk:
    """构造流式工具调用 chunk(合并后 langchain 自动组装 tool_calls)"""
    return AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": name, "args": args_json, "id": call_id,
            "index": 0, "type": "tool_call_chunk",
        }],
    )


async def _stub_web_search(args, ctx) -> str:
    """web_search 技能桩: 记录上下文并返回固定结果"""
    _stub_web_search.last_ctx = ctx
    return f"搜索结果: {args.query}"


_stub_web_search.last_ctx = None


@pytest.fixture
def stub_llm(monkeypatch):
    """打桩模型解析与 LLM 构造(默认两轮: 工具调用→答案), 返回 FakeLLM 供用例改写"""
    fake = _FakeLLM(
        rounds=[
            [_tool_call_chunk("web_search", '{"query": "hello"}', "call_1")],
            [AIMessageChunk(content="最终"), AIMessageChunk(content="答案")],
        ]
    )
    fake.direct_answer = [AIMessageChunk(content="兜底答案")]

    async def _resolve(self, user_id, model_type):
        return ResolvedModel(model_id="stub_model")

    async def _get_llm(self, user_id, streaming=True, model_type=None):
        return fake

    monkeypatch.setattr(UserModelService, "resolve_model", _resolve)
    monkeypatch.setattr(UserModelService, "get_llm_by_user_id", _get_llm)
    monkeypatch.setattr(SKILLS["web_search"], "func", _stub_web_search)
    return fake


@pytest.fixture
async def clean_agent_state(test_admin: dict):
    """用例级隔离: 记录前置 Agent 名单, 测后清理新增行(不动内置种子)"""
    before = {a.id for a in await AgentDao().list_all()}
    yield test_admin["id"]
    for agent in await AgentDao().list_all():
        if agent.id not in before:
            await AgentDao().delete(agent)


# ################ 接口级: 技能清单与内置种子 ################


async def test_skills_endpoint(client):
    """技能清单: 内置 4 只读技能, 接口登录可访问"""
    resp = await client.get("/agent/skills")
    assert resp.status_code == 200
    data = resp.json()
    names = {s["name"] for s in data}
    assert {"web_search", "ocr_image", "file_search", "rag_qa"} <= names
    assert all(s["capability"] == "read" for s in data)


async def test_builtin_agents_seeded(client):
    """内置双 Agent 幂等播种: 通用助手(无技能)/全能智能体(全技能)"""
    resp = await client.get("/agent/agents")
    assert resp.status_code == 200
    agents = {a["id"]: a for a in resp.json()}
    assert BUILTIN_CHAT_ID in agents and BUILTIN_AGENT_ID in agents
    assert agents[BUILTIN_CHAT_ID]["skills"] == []
    assert agents[BUILTIN_AGENT_ID]["skills"] == list(SKILLS.keys())
    assert agents[BUILTIN_AGENT_ID]["is_builtin"] is True


async def test_skills_requires_login(anon_client):
    """未登录访问技能清单: 401"""
    resp = await anon_client.get("/agent/skills")
    assert resp.status_code == 401


# ################ 接口级: CRUD 与可见性 ################


async def test_agent_crud_lifecycle(client, clean_agent_state):
    """创建→更新→删除自建 Agent; 非法技能名单被拒"""
    resp = await client.post(
        "/agent/agents",
        json=AgentCreate(
            name=f"测试助手_{uuid.uuid4().hex[:6]}",
            description="desc",
            default_prompt="你是测试助手",
            skills=["web_search"],
            is_public=False,
        ).model_dump(),
    )
    assert resp.status_code == 200, resp.text
    agent_id = resp.json()["id"]

    resp = await client.put(
        f"/agent/agents/{agent_id}",
        json=AgentUpdate(name="改名助手", skills=["web_search", "rag_qa"]).model_dump(exclude_none=True),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名助手"
    assert resp.json()["skills"] == ["web_search", "rag_qa"]

    # 非法技能名单: 400
    resp = await client.post(
        "/agent/agents",
        json=AgentCreate(name=f"坏助手_{uuid.uuid4().hex[:6]}", skills=["no_such_skill"]).model_dump(),
    )
    assert resp.status_code == 400
    assert "no_such_skill" in resp.json()["detail"]

    resp = await client.delete(f"/agent/agents/{agent_id}")
    assert resp.status_code == 200
    resp = await client.get(f"/agent/agents/{agent_id}")
    assert resp.status_code == 404


async def test_builtin_agent_protected(client):
    """内置 Agent 不可删除"""
    resp = await client.delete(f"/agent/agents/{BUILTIN_CHAT_ID}")
    assert resp.status_code == 400
    assert "内置" in resp.json()["detail"]


async def test_visibility_isolation(client, user_client, clean_agent_state):
    """管理员私有 Agent: 本人/管理端可见, 普通用户不可见不可取"""
    resp = await client.post(
        "/agent/agents",
        json=AgentCreate(
            name=f"私有助手_{uuid.uuid4().hex[:6]}",
            skills=[],
            is_public=False,
        ).model_dump(),
    )
    assert resp.status_code == 200
    agent_id = resp.json()["id"]

    # 管理端全量可见
    resp = await client.get("/agent/agents/all")
    assert agent_id in {a["id"] for a in resp.json()}

    # 普通用户: 列表不可见 + 详情 404
    resp = await user_client.get("/agent/agents")
    assert agent_id not in {a["id"] for a in resp.json()}
    resp = await user_client.get(f"/agent/agents/{agent_id}")
    assert resp.status_code == 404

    # 普通用户不可改他人 Agent
    resp = await user_client.put(
        f"/agent/agents/{agent_id}", json=AgentUpdate(name="越权改名").model_dump(exclude_none=True)
    )
    assert resp.status_code in (400, 404)


async def test_user_create_own_agent(user_client, clean_agent_state):
    """普通用户登录即可自建/自改/自删 Agent"""
    resp = await user_client.post(
        "/agent/agents",
        json=AgentCreate(name=f"用户助手_{uuid.uuid4().hex[:6]}", skills=["file_search"]).model_dump(),
    )
    assert resp.status_code == 200, resp.text
    agent_id = resp.json()["id"]
    resp = await user_client.delete(f"/agent/agents/{agent_id}")
    assert resp.status_code == 200


# ################ 执行循环: tool-calling ################


async def _make_conversation(user_id: str, agent_id: str) -> str:
    """直建测试会话(绑定 agent), 返回会话ID"""
    return await ConversationService().create(
        user_id, ConversationCreate(title="pytest-agent", agent_id=agent_id)
    )


async def _collect_stream(conversation_id: str, user_id: str, agent_id: str, message: str) -> list:
    """服务级直调执行循环, 收集全部 StreamOne 事件(不经 HTTP/SSE, 规避
    ASGITransport 下 sse-starlette 断开监听与 BaseHTTPMiddleware 的已知竞态)"""
    from module_agent.dependencies.agent import get_agent_runner_service
    from module_agent.service.runner import AgentChatRequest

    runner = get_agent_runner_service()
    events = []
    async for item in runner.chat_stream(
        conversation_id=conversation_id,
        user_id=user_id,
        agent_id=agent_id,
        request=AgentChatRequest(message=message, agent_id=agent_id),
    ):
        events.append(item)
    return events


async def test_chat_tool_call_roundtrip(test_admin, stub_llm):
    """执行循环: 工具调用→回填→最终答案, 事件流与消息落库完整"""
    conversation_id = await _make_conversation(test_admin["id"], BUILTIN_AGENT_ID)
    try:
        events = await _collect_stream(
            conversation_id, test_admin["id"], BUILTIN_AGENT_ID, "帮我搜索 hello"
        )
        by_type = {e.stream_event_type.value for e in events}
        assert "tool_call" in by_type and "answer" in by_type
        # 工具调用事件: data 结构化载荷 + 结果文本
        call_events = [e for e in events if e.stream_event_type.value == "tool_call"]
        assert any(e.data and e.data.get("tool_name") == "web_search" for e in call_events)
        assert any("搜索结果: hello" in e.content for e in call_events)
        # 最终答案为流式增量拼接
        answer = "".join(e.content for e in events if e.stream_event_type.value == "answer")
        assert answer == "最终答案"

        # bind_tools 挂载了全部注册技能
        assert stub_llm.bound_tools is not None
        assert len(stub_llm.bound_tools) == len(SKILLS)

        # 第二轮收到的消息尾部为 ToolMessage 回填(含工具结果)
        round2 = stub_llm.snapshots[1]
        assert isinstance(round2[-1], ToolMessage)
        assert "搜索结果: hello" in round2[-1].content
        # 系统提示置首, 历史含本轮用户消息
        assert round2[0].type == "system"
        assert any(isinstance(m, HumanMessage) for m in round2)

        # 技能执行拿到了正确用户上下文
        assert _stub_web_search.last_ctx is not None
        assert _stub_web_search.last_ctx.user_id == test_admin["id"]

        # 消息落库: 用户 + 助手(含工具过程区块)
        from common.utils.db.schema.pagination import PaginationParams

        page = await ChatMessageService().list_by_conversation(
            conversation_id, PaginationParams(page=1, size=50)
        )
        roles = [m.role for m in page.items]
        assert roles.count("user") >= 1 and roles.count("assistant") >= 1
        assistant = [m for m in page.items if m.role == "assistant"][-1]
        assert "最终答案" in assistant.content
        assert any(
            b.get("stream_event_type") == "tool_call" for b in (assistant.blocks or [])
        )
    finally:
        await ConversationService().delete(conversation_id)


async def test_chat_pure_answer_no_tools(test_admin, stub_llm):
    """无技能 Agent(通用助手): 不绑定工具, 单轮直出答案"""
    conversation_id = await _make_conversation(test_admin["id"], BUILTIN_CHAT_ID)
    try:
        events = await _collect_stream(conversation_id, test_admin["id"], "", "你好")
        answer = "".join(e.content for e in events if e.stream_event_type.value == "answer")
        # 无工具路径: direct_answer 流式输出
        assert answer == "兜底答案"
        assert stub_llm.bound_tools is None
        assert stub_llm.snapshots, "无工具路径也应收到消息列表"
    finally:
        await ConversationService().delete(conversation_id)


async def test_chat_max_rounds_guard(test_admin, stub_llm):
    """防失控: 持续要求工具调用时, 最后一轮强制直出答案"""
    # 7 轮工具调用 + 第 8 轮强制无工具(direct_answer 路径)
    stub_llm.rounds = [
        [_tool_call_chunk("web_search", '{"query": "q"}', f"call_{i}")]
        for i in range(7)
    ]
    conversation_id = await _make_conversation(test_admin["id"], BUILTIN_AGENT_ID)
    try:
        events = await _collect_stream(
            conversation_id, test_admin["id"], BUILTIN_AGENT_ID, "一直调工具"
        )
        status_texts = [e.content for e in events if e.stream_event_type.value == "status"]
        assert any("已达工具调用轮数上限" in t for t in status_texts)
        answer = "".join(e.content for e in events if e.stream_event_type.value == "answer")
        assert answer == "兜底答案"
        # 7 轮 bind 调用 + 1 轮直连
        assert len(stub_llm.snapshots) == 8
    finally:
        await ConversationService().delete(conversation_id)


async def test_chat_requires_login(anon_client):
    """未登录对话: 401"""
    resp = await anon_client.post(
        "/agent/chat/any/chat", json={"message": "hi"}
    )
    assert resp.status_code == 401


async def test_chat_unknown_conversation(test_admin, stub_llm):
    """会话不存在: 流内 ERROR 事件"""
    events = await _collect_stream(
        "no_such_conversation", test_admin["id"], BUILTIN_CHAT_ID, "hi"
    )
    assert any(e.stream_event_type.value == "error" for e in events)
