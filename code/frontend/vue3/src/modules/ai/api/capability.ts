// src/modules/ai/api/capability.ts
// Model 层能力注册表 API(REQ-018)
import { http_base_server } from '@/common/api/http';
import type { AiCapabilityItem } from '../types/capability';

/**
 * 能力注册表(双源合一): static_func 代码注册表 + 各 model_type 三作用域解析结果
 * 登录可见; Skill 声明的 capability_key 均可在此核对解析结果
 */
export const listAiCapabilities = () => {
  return http_base_server.get<AiCapabilityItem[]>('/ai/capabilities');
};
