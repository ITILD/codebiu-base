// src/modules/agent/api/agent.ts
// 智能体 API(REQ-013): 助手 CRUD / 技能清单 / 智能体流式对话(AG-UI 协议)
import { http_base_server } from '@/common/api/http';
import { streamAguiEvents } from '@/common/api/aguiStream';
import type { AguiStreamCallbacks } from '@/common/api/aguiStream';
import type { AgentInfo, AgentCreateReq, AgentUpdateReq, AgentChatReq, SkillInfo } from '../types';

/**
 * 我可见的智能体列表(公开 + 本人创建, AI 助手页选择器用)
 */
export const listAgents = () => {
  return http_base_server.get<AgentInfo[]>('/agent/agents');
};

/**
 * 全部智能体列表(管理端点, 需 agent:manage 权限)
 */
export const listAllAgents = () => {
  return http_base_server.get<AgentInfo[]>('/agent/agents/all');
};

/**
 * 技能注册表清单
 */
export const listSkills = () => {
  return http_base_server.get<SkillInfo[]>('/agent/skills');
};

/**
 * 创建智能体(登录即可)
 */
export const createAgent = (data: AgentCreateReq) => {
  return http_base_server.post<AgentInfo>('/agent/agents', data);
};

/**
 * 更新智能体(创建者或管理员; 内置仅管理员)
 */
export const updateAgent = (agentId: string, data: AgentUpdateReq) => {
  return http_base_server.put<AgentInfo>(`/agent/agents/${agentId}`, data);
};

/**
 * 删除智能体(创建者或管理员; 内置不可删)
 */
export const deleteAgent = (agentId: string) => {
  return http_base_server.delete<{ detail: string }>(`/agent/agents/${agentId}`);
};

/**
 * 智能体流式对话(AG-UI 协议 SSE, 事件流与 rag 聊天同构, 由 useAguiMessages 聚合)
 */
export const sendAgentChatAguiStream = async (
  conversationId: string,
  request: AgentChatReq,
  callbacks: AguiStreamCallbacks,
) => {
  return streamAguiEvents(
    `/base_server/agent/chat/${conversationId}/chat`,
    request,
    callbacks,
  );
};
