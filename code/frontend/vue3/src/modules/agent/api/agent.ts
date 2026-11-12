// src/modules/agent/api/agent.ts
// 智能体/能力平台 API: 助手 CRUD / 技能清单与调试 / 调用观测 / job 编排(REQ-013/REQ-018)
import { http_base_server } from '@/common/api/http';
import { streamAguiEvents } from '@/common/api/aguiStream';
import type { AguiStreamCallbacks } from '@/common/api/aguiStream';
import type { PaginationResponse } from '@/common/types/common';
import type {
  AgentInfo,
  AgentCreateReq,
  AgentUpdateReq,
  AgentChatReq,
  SkillInfo,
  SkillInvokeEnvelope,
  InvocationItem,
  InvocationDetail,
  InvocationListParams,
  AgentJobInfo,
  JobRunDetail,
  JobRunListItem,
  JobRunListParams,
  JobRunResumeResult,
  CustomSkillInfo,
  CustomSkillDetail,
  CustomSkillCreateReq,
  CustomSkillUpdateReq,
  SkillHubPackage,
  SkillHubImportResult,
  McpServerInfo,
  McpRegisterReq,
  UsageSummary,
} from '../types';

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
 * 技能注册表清单(Manifest 视图; key 为全局键, name 为展示名)
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

// ===== 能力平台: Skill 调试 / 调用观测(REQ-018) =====

/**
 * Skill 调试台: 直调任意 Skill, 返回统一信封
 * 需 agent:skill:invoke 权限, 普通用户 403 属预期(调用方需优雅处理)
 */
export const invokeSkill = (
  skillKey: string,
  input: Record<string, unknown>,
  mode: string = 'auto',
) => {
  return http_base_server.post<SkillInvokeEnvelope>(
    `/agent/skills/${encodeURIComponent(skillKey)}/invoke`,
    { input, mode },
  );
};

/**
 * 分页查询本人 Skill 调用记录(支持技能键/状态过滤)
 */
export const listInvocations = (params: InvocationListParams) => {
  return http_base_server.get<PaginationResponse<InvocationItem>>('/agent/invocations', { params });
};

/**
 * 查询调用记录详情(本人可查)
 */
export const getInvocation = (invocationId: string) => {
  return http_base_server.get<InvocationDetail>(`/agent/invocations/${invocationId}`);
};

// ===== 能力平台: job Agent 编排(REQ-018) =====

/**
 * 内置 job Agent 清单(static_agent Manifest: 步骤声明/条件/资源策略)
 */
export const listAgentJobs = () => {
  return http_base_server.get<AgentJobInfo[]>('/agent/jobs');
};

/**
 * 分页查询本人 job 运行历史(REQ-018 批次 2; 支持 agent_key/状态过滤)
 */
export const listJobRuns = (params: JobRunListParams) => {
  return http_base_server.get<PaginationResponse<JobRunListItem>>('/agent/job-runs', { params });
};

/**
 * 查询 job 运行详情(步骤状态含 when/skip_if 判定结果与展开项明细)
 */
export const getJobRun = (jobRunId: string) => {
  return http_base_server.get<JobRunDetail>(`/agent/job-runs/${jobRunId}`);
};

/**
 * 断点续跑失败的 job(仅失败/取消态可续; 已成功项直接复用)
 * 需 agent:skill:invoke 权限
 */
export const resumeJobRun = (jobRunId: string) => {
  return http_base_server.post<JobRunResumeResult>(`/agent/job-runs/${jobRunId}/resume`);
};

// ===== 能力平台: 自定义 prompt Skill(REQ-018, 写操作需 agent:skill:update 权限) =====

/**
 * 自定义 Skill 列表(本人创建; 管理员见全量)
 */
export const listCustomSkills = () => {
  return http_base_server.get<CustomSkillInfo[]>('/agent/skills/custom');
};

/**
 * 自定义 Skill 详情(最新版本快照回显: 模板原文/字段声明/输出格式, 编辑表单数据源)
 */
export const getCustomSkill = (skillId: string) => {
  return http_base_server.get<CustomSkillDetail>(`/agent/skills/custom/${skillId}`);
};

/**
 * 创建自定义 prompt Skill 草稿(usr 命名空间)
 */
export const createCustomSkill = (data: CustomSkillCreateReq) => {
  return http_base_server.post<{ skill_id: string; key: string; status: string }>(
    '/agent/skills/custom',
    data,
  );
};

/**
 * 更新自定义 Skill(已发布则生成新版本快照并重注册生效)
 */
export const updateCustomSkill = (skillId: string, data: CustomSkillUpdateReq) => {
  return http_base_server.put<{ skill_id: string; key: string; version: string }>(
    `/agent/skills/custom/${skillId}`,
    data,
  );
};

/**
 * 发布自定义 Skill(注册表登记后方可调用)
 */
export const publishCustomSkill = (skillId: string) => {
  return http_base_server.post<{ skill_id: string; key: string; status: string }>(
    `/agent/skills/custom/${skillId}/publish`,
  );
};

/**
 * 下线自定义 Skill(注册表反注册, 新调用被拒; 历史记录保留可追溯)
 */
export const deprecateCustomSkill = (skillId: string) => {
  return http_base_server.delete<{ skill_id: string; key: string; status: string }>(
    `/agent/skills/custom/${skillId}`,
  );
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

// ===== 外部能力: Skill Hub 包 / MCP server(REQ-018 批次 3, 写操作需 agent:skill:update 权限) =====

/**
 * Skill Hub 社区包清单(pack.* 命名空间, 拆解产物与注册状态)
 */
export const listSkillHubPackages = () => {
  return http_base_server.get<SkillHubPackage[]>('/agent/skill-hub/packages');
};

/**
 * 导入社区 SKILL.md 包(zip 上传, 拆解注册: 指令→pack.{包}.main, 脚本→pack.{包}.{名})
 * 需 agent:skill:update 权限; 失败 detail(缺少 SKILL.md/包已存在等)由调用方展示
 */
export const importSkillHubPackage = (file: File) => {
  const formData = new FormData();
  formData.append('file', file, file.name);
  return http_base_server.post<SkillHubImportResult>(
    '/agent/skill-hub/packages',
    formData,
  );
};

/**
 * 删除社区包(注册表移除该包全部技能, 历史调用记录保留)
 * 需 agent:skill:update 权限
 */
export const removeSkillHubPackage = (namespace: string) => {
  return http_base_server.delete<{ namespace: string; status: string }>(
    `/agent/skill-hub/packages/${encodeURIComponent(namespace)}`,
  );
};

/**
 * 已登记 MCP server 清单(mcp.* 命名空间, 反射注册的 tools 与状态)
 */
export const listMcpServers = () => {
  return http_base_server.get<McpServerInfo[]>('/agent/mcp/servers');
};

/**
 * 登记 MCP server(stdio): 连接验证 + tools/list 反射注册为 mcp.{name}.{tool} Skill
 * 需 agent:skill:update 权限; 连接/握手失败 detail 由调用方展示
 */
export const registerMcpServer = (data: McpRegisterReq) => {
  return http_base_server.post<{ namespace: string; tools: string[] }>(
    '/agent/mcp/servers',
    data,
  );
};

/**
 * 移除 MCP server(注册表反注册全部 tools)
 * 需 agent:skill:update 权限
 */
export const removeMcpServer = (namespace: string) => {
  return http_base_server.delete<{ namespace: string; status: string }>(
    `/agent/mcp/servers/${encodeURIComponent(namespace)}`,
  );
};

// ===== 用量统计(REQ-018 批次 3, 需 agent:skill:read 权限) =====

/**
 * 用量与计费口径汇总(双粒度): 按技能调用量/成功率/降级数/tokens/时长 + 按 job 运行量/成功率
 */
export const getUsageSummary = (days: number) => {
  return http_base_server.get<UsageSummary>('/agent/usage/summary', {
    params: { days },
  });
};
