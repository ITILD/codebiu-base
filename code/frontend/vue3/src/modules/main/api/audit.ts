// 操作审计日志接口(REQ-009, 对应后端 /audit_logs)
import { http_base_server } from '@/common/api/http';
import type { PaginationParams, PaginationResponse } from '@/common/types/common';
import type { AuditLog } from '../types/audit';

/** 审计日志列表过滤参数 */
export type AuditListParams = PaginationParams & {
  /** 操作用户ID精确过滤 */
  user_id?: string;
  /** 用户名模糊过滤 */
  username?: string;
  /** HTTP 方法过滤(POST/PUT/DELETE/PATCH) */
  method?: string;
  /** 请求路径关键字模糊过滤 */
  keyword?: string;
  /** 起始时间(ISO 8601) */
  start?: string;
  /** 截止时间(ISO 8601) */
  end?: string;
}

/** 分页查询操作审计日志(记录时间倒序) */
export const listAuditLogs = (params: AuditListParams) => {
  return http_base_server.get<PaginationResponse<AuditLog>>('/audit_logs/list', { params });
};
