// 成本与用量治理接口, 对应后端 module_rag.controller.usage
// stats/records/conversations 仅系统管理员; last 为用户自查本轮用量
import { http_base_server } from '@/common/api/http';
import type { PaginationParams, PaginationResponse } from '@/common/types/common';
import type {
  UsageStats,
  UsageRecordItem,
  UsageConversationItem,
  LastUsage,
} from '../types/usage';

/**
 * 获取问答 token 用量与成本统计(管理员)
 * @param params.days 统计天数(含当天)
 * @param params.user_id 可选按用户过滤
 */
export const getUsageStats = (params: { days: number; user_id?: string }) => {
  return http_base_server.get<UsageStats>('/rag/usage/stats', {
    params: {
      days: String(params.days),
      ...(params.user_id ? { user_id: params.user_id } : {}),
    },
  });
};

/**
 * 用量明细分页(管理员): 每轮问答的 token 与成本记录
 * @param params 分页 + 可选过滤(天数/用户/模型标识)
 */
export const getUsageRecords = (
  params: PaginationParams & { days?: number; user_id?: string; model_name?: string }
) => {
  return http_base_server.get<PaginationResponse<UsageRecordItem>>('/rag/usage/records', {
    params: { ...params },
  });
};

/**
 * 对话维度用量聚合分页(管理员): 每个会话的轮次/token/成本与用户
 */
export const getUsageConversations = (params: PaginationParams & { user_id?: string }) => {
  return http_base_server.get<PaginationResponse<UsageConversationItem>>(
    '/rag/usage/conversations',
    { params: { ...params } }
  );
};

/**
 * 查询本人在指定会话最近一轮的用量(token 与费用)
 * @param conversationId 会话ID
 */
export const getLastUsage = (conversationId: string) => {
  return http_base_server.get<LastUsage | null>('/rag/usage/last', {
    params: { conversation_id: conversationId },
  });
};
