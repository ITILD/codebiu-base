// src/modules/main/api/codegen.ts
// 代码生成器接口(对应后端 /codegen): 表清单 → 表结构 → 智能建议 → 预览 → 生成
import { http_base_server } from '@/common/api/http';
import type {
  CodegenGenerateRequest,
  CodegenGenerateResult,
  CodegenPreviewRequest,
  CodegenPreviewResult,
  CodegenSuggestRequest,
  CodegenSuggestResult,
  CodegenTable,
  CodegenTableDetail,
} from '../types/codegen';

/** 查询数据表列表(表名/注释关键字过滤) */
export const listCodegenTables = (keyword?: string) => {
  return http_base_server.get<{ items: CodegenTable[] }>('/codegen/tables', {
    params: { keyword },
  });
};

/** 获取单表结构(字段元数据) */
export const getCodegenTable = (tableName: string) => {
  return http_base_server.get<CodegenTableDetail>(`/codegen/tables/${encodeURIComponent(tableName)}`);
};

/** 智能建议字段配置(use_ai=false 时后端走模板规则) */
export const suggestCodegen = (data: CodegenSuggestRequest) => {
  return http_base_server.post<CodegenSuggestResult>('/codegen/suggest', data);
};

/** 预览生成文件(不落盘) */
export const previewCodegen = (data: CodegenPreviewRequest) => {
  return http_base_server.post<CodegenPreviewResult>('/codegen/preview', data);
};

/** 生成代码(按 overwrite 决定是否覆盖已存在文件) */
export const generateCodegen = (data: CodegenGenerateRequest) => {
  return http_base_server.post<CodegenGenerateResult>('/codegen/generate', data);
};
