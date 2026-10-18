// src/modules/ai/api/model_config.ts
import { http_base_server } from '@/common/api/http';
import { API_PREFIX, authFetch } from '@/common/api/authFetch';
import { extractHttpErrorMessage } from '@/common/api/httpError';
import {
  type InfiniteScrollParams,
  type InfiniteScrollResponse,
  type PaginationParams,
  type PaginationResponse,
} from '@/common/types/common';
import type {
  ModelConfig,
  ModelConfigCreate,
  ModelConfigUpdate,
  ModelCustomTestResponse,
  ModelMediaTestResponse,
  ModelTestResponse,
} from '../types/model_config';

/**
 * 创建新模型配置
 * @param modelConfig 模型配置数据
 * @returns 创建的模型配置ID
 */
export const createModelConfig = (modelConfig: ModelConfigCreate) => {
  return http_base_server.post<object>('/ai/model-configs', modelConfig);
};

/**
 * 删除模型配置
 * @param modelConfigId 模型配置ID
 */
export const deleteModelConfig = (modelConfigId: string) => {
  return http_base_server.delete<void>(`/ai/model-configs/${modelConfigId}`);
};

/**
 * 更新模型配置
 * @param modelConfigId 模型配置ID
 * @param modelConfig 模型配置数据
 */
export const updateModelConfig = (modelConfigId: string, modelConfig: ModelConfigUpdate) => {
  return http_base_server.put<void>(`/ai/model-configs/${modelConfigId}`, modelConfig);
};

/**
 * 获取单个模型配置详情
 * @param modelConfigId 模型配置ID
 * @returns 模型配置详情
 */
export const getModelConfig = (modelConfigId: string) => {
  return http_base_server.get<ModelConfig>(`/ai/model-configs/${modelConfigId}`);
};

/**
 * 分页查询模型配置列表
 * @param params 分页参数
 * @returns 分页响应结果
 */
export const listModelConfigs = (params: PaginationParams) => {
  return http_base_server.get<PaginationResponse<ModelConfig>>('/ai/model-configs/list', { params });
};

/**
 * 无限滚动加载模型配置列表
 * @param params 滚动加载参数
 * @returns 滚动加载响应结果
 */
export const infiniteScrollModelConfigs = (params: InfiniteScrollParams) => {
  return http_base_server.get<InfiniteScrollResponse<ModelConfig>>('/ai/model-configs/scroll', {
    params
  });
};

/**
 * 模型能力测试(问答/结构化/多模态/向量化/重排)
 * 结果持久化到 model_config.check_result, 供能力标签常驻展示
 * @param modelId 模型配置ID
 * @param capability 可选, 仅测试指定能力(缺省测试该类型全部能力)
 */
export const testModelCapability = (modelId: string, capability?: string) => {
  return http_base_server.post<ModelTestResponse>('/ai/llm/test-by-model-id', {
    model_id: modelId,
    capability: capability || null,
  });
};

/**
 * 模型单独测试(自定义参数单次真实调用: chat 问答/向量化/重排打分)
 * @param payload 按模型类型携带 question / text / query+documents
 */
export const testModelCustom = (payload: {
  model_id: string;
  question?: string;
  text?: string;
  query?: string;
  documents?: string[];
}) => {
  return http_base_server.post<ModelCustomTestResponse>('/ai/llm/test-custom', payload);
};

/**
 * TTS 模型单独测试(自定义文本合成语音)
 * @param modelId 模型配置ID
 * @param text 待合成文本
 * @param speed 语速(0.5~2.0)
 * @returns Blob(audio/wav) 供试听
 */
export const testTtsModel = async (modelId: string, text: string, speed = 1.0) => {
  const resp = await authFetch(`${API_PREFIX}/ai/llm/test-tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, text, speed })
  });
  if (!resp.ok) throw new Error(await extractHttpErrorMessage(resp));
  return resp.blob();
};

/**
 * ASR 模型单独测试(上传音频识别)
 * @param modelId 模型配置ID
 * @param audio 音频文件
 */
export const testAsrModel = (modelId: string, audio: File | Blob) => {
  const formData = new FormData();
  formData.append('model_id', modelId);
  formData.append('audio', audio);
  return http_base_server.post<ModelMediaTestResponse>('/ai/llm/test-asr', formData);
};

/**
 * OCR 模型单独测试(上传图片识别)
 * @param modelId 模型配置ID
 * @param image 图片文件
 */
export const testOcrModel = (modelId: string, image: File | Blob) => {
  const formData = new FormData();
  formData.append('model_id', modelId);
  formData.append('image', image);
  return http_base_server.post<ModelMediaTestResponse>('/ai/llm/test-ocr', formData);
};

/**
 * 提交全库 chunk 重向量化任务(系统管理员)
 * 以指定/当前生效的默认公共向量化模型, 重算 Milvus 中所有 chunk 向量
 * @param modelId 目标模型配置ID(留空使用当前生效的默认公共向量化模型)
 * @returns Celery 任务ID
 */
export const revectorizeChunks = (modelId?: string) => {
  return http_base_server.post<{ task_id: string; message: string }>(
    '/rag/project-document-chunks/revectorize',
    { model_id: modelId || null }
  );
};

/**
 * 查询全库重向量化任务进度(系统管理员)
 * @param taskId POST /revectorize 返回的任务ID
 * @returns state=PROGRESS 时 meta 含 total/processed/chunks/model
 */
export const getRevectorizeStatus = (taskId: string) => {
  return http_base_server.get<{
    task_id: string;
    state: string;
    meta?: { total: number; processed: number; chunks: number; model: string; dim_changed: boolean };
    error?: string;
  }>(`/rag/project-document-chunks/revectorize/status/${taskId}`);
};
