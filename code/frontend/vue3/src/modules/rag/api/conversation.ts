// src/modules/rag/api/conversation.ts
// 知识库对话 API(对话管理 + RAG 流式聊天)
// 流式聊天统一走 AG-UI 协议(官方 ag-ui-protocol 事件流, 见 @/common/api/aguiStream)
import { http_base_server } from '@/common/api/http';
import { streamAguiEvents } from '@/common/api/aguiStream';
import type { AguiStreamCallbacks } from '@/common/api/aguiStream';
import { createStorageUploader } from '@/common/utils/storageUpload';
import type { MultipartPart } from '@/common/utils/storageUpload';
import type { PaginationParams, PaginationResponse } from '@/common/types/common';
import type {
  Conversation,
  ConversationCreate,
  ConversationUpdate,
  ChatMessage,
  RagChatRequest,
  ProjectDocument,
  ConversationSummary,
} from '../types';

/**
 * 创建对话
 * @param data 对话数据(标题/关联知识库)
 * @returns 对话ID
 */
export const createConversation = (data: ConversationCreate) => {
  return http_base_server.post<string>('/rag/conversations', data);
};

/**
 * 获取我的对话列表(知识库问答页使用, 排除智能体对话)
 * @param params 分页参数
 */
export const listMyConversations = (params: PaginationParams) => {
  return http_base_server.get<PaginationResponse<Conversation>>(
    '/rag/conversations/my',
    { params: { ...params, scope: 'rag' } }
  );
};

/**
 * 获取我的全部对话列表(问答页使用: 智能体会话与历史知识库会话统一展示)
 * @param params 分页参数
 */
export const listAllConversations = (params: PaginationParams) => {
  return http_base_server.get<PaginationResponse<Conversation>>(
    '/rag/conversations/my',
    { params: { ...params, scope: 'all' } }
  );
};

/**
 * 获取我的智能体对话列表(AI 助手页 agent 模式使用, 仅 agent_id 非空的会话)
 * @param params 分页参数
 */
export const listAgentConversations = (params: PaginationParams) => {
  return http_base_server.get<PaginationResponse<Conversation>>(
    '/rag/conversations/my',
    { params: { ...params, scope: 'agent' } }
  );
};

/**
 * 获取对话详情
 * @param conversationId 对话ID
 */
export const getConversation = (conversationId: string) => {
  return http_base_server.get<Conversation>(
    `/rag/conversations/${conversationId}`
  );
};

/**
 * 更新对话(标题/关联知识库)
 * @param conversationId 对话ID
 * @param data 更新数据
 */
export const updateConversation = (
  conversationId: string,
  data: ConversationUpdate
) => {
  return http_base_server.put<void>(
    `/rag/conversations/${conversationId}`,
    data
  );
};

/**
 * 删除对话(同时删除关联消息)
 * @param conversationId 对话ID
 */
export const deleteConversation = (conversationId: string) => {
  return http_base_server.delete<void>(`/rag/conversations/${conversationId}`);
};

/**
 * 获取对话消息列表
 * @param conversationId 对话ID
 * @param params 分页参数
 */
export const listConversationMessages = (
  conversationId: string,
  params: PaginationParams
) => {
  return http_base_server.get<PaginationResponse<ChatMessage>>(
    `/rag/conversations/${conversationId}/messages`,
    { params }
  );
};

/**
 * 总结历史对话并生成标题
 * @param conversationId 对话ID
 */
export const summarizeConversation = (conversationId: string) => {
  return http_base_server.post<ConversationSummary>(
    `/rag/rag-chat/${conversationId}/summarize`
  );
};

/** 问答附件上传模式缓存(direct=预签名直传 / proxy=服务端中转) */
interface AttachmentUploadMode {
  mode: 'direct' | 'proxy';
  part_size: number;
  max_size: number;
}
let attachmentUploadModeCache: AttachmentUploadMode | null = null;

/** 查询问答附件上传模式(首次调用获取并缓存) */
const getAttachmentUploadMode = async (): Promise<AttachmentUploadMode> => {
  if (!attachmentUploadModeCache) {
    attachmentUploadModeCache = await http_base_server.get<AttachmentUploadMode>(
      '/rag/rag-chat/attachments/upload-mode'
    );
  }
  return attachmentUploadModeCache;
};

/** 分片上传初始化响应(mode=direct 时 part_urls 与分片号一一对应) */
interface AttachmentMultipartInit {
  is_existing: boolean;
  upload_id: string | null;
  part_size: number;
  mode: 'direct' | 'proxy';
  part_urls: string[] | null;
  /** 服务端确认的落库文件名(同名自动加序号) */
  filename?: string | null;
}

/** 初始化问答附件预签名上传(登记到临时知识库, 同名自动加序号) */
const initAttachmentMultipart = (data: {
  filename: string;
  file_size_bytes: number;
  content_hash: string;
  content_type?: string;
}) => {
  return http_base_server.post<AttachmentMultipartInit>(
    '/rag/rag-chat/attachments/multipart/init',
    data
  );
};

/** proxy 模式分片中转 */
const uploadAttachmentPart = (
  uploadId: string,
  partNumber: number,
  content: ArrayBuffer
) => {
  return http_base_server.putRaw<MultipartPart>(
    `/rag/rag-chat/attachments/multipart/${encodeURIComponent(uploadId)}/parts/${partNumber}`,
    content,
    { headers: { 'Content-Type': 'application/octet-stream' } }
  );
};

/** 完成问答附件上传并登记文档(后端自动派发解析任务) */
const completeAttachmentMultipart = (
  uploadId: string,
  data: {
    filename: string;
    file_size_bytes: number;
    parts: MultipartPart[];
  }
) => {
  return http_base_server.post<ProjectDocument>(
    `/rag/rag-chat/attachments/multipart/${encodeURIComponent(uploadId)}/complete`,
    data
  );
};

/** 秒传登记(内容已存在时直接建文档) */
const instantRegisterAttachment = (data: {
  name: string;
  content_hash: string;
  file_size_bytes: number;
  mime_type?: string;
}) => {
  return http_base_server.post<ProjectDocument>(
    '/rag/rag-chat/attachments/upload-complete',
    data
  );
};

/** 问答附件统一存储上传器(预签名直传优先, proxy 自动走服务端中转) */
const chatAttachmentUploader = createStorageUploader<void, ProjectDocument>({
  getMode: getAttachmentUploadMode,
  init: (file, contentHash) =>
    initAttachmentMultipart({
      filename: file.name,
      file_size_bytes: file.size,
      content_hash: contentHash,
      content_type: file.type || undefined,
    }),
  uploadPart: uploadAttachmentPart,
  complete: (file, uploadId, parts, _ctx, filename) =>
    completeAttachmentMultipart(uploadId, {
      filename: filename || file.name,
      file_size_bytes: file.size,
      parts,
    }),
  instant: (file, contentHash, _ctx, filename) =>
    instantRegisterAttachment({
      name: filename || file.name,
      content_hash: contentHash,
      file_size_bytes: file.size,
      mime_type: file.type || undefined,
    }),
});

/**
 * 上传问答附件: 自动存入个人默认临时知识库并派发解析入库任务
 * (预签名直传优先, 解析→分块→向量化与知识库文档同链路), 入库进度经
 * getRagDocumentIngestProgress 轮询; 完成后问答检索自动命中
 * @param file 本地文件
 * @returns 文档元数据(parse_task_warning 携带解析任务派发警告)
 */
export const uploadChatAttachment = (file: File) => {
  return chatAttachmentUploader(file);
};

/**
 * RAG 流式聊天(AG-UI 协议 SSE)
 * 事件为 AG-UI 标准事件流(RUN_STARTED / TEXT_MESSAGE / TOOL_CALL / CUSTOM 等),
 * 由 useAguiMessages 聚合为消息内容; 交互卡片响应通过 interaction_response 续跑流程
 * @param conversationId 对话ID
 * @param request 聊天请求
 * @param callbacks 事件回调组
 * @returns 中止控制器
 */
export const sendRagChatAguiStream = async (
  conversationId: string,
  request: RagChatRequest,
  callbacks: AguiStreamCallbacks
) => {
  return streamAguiEvents(
    `/base_server/rag/rag-chat/${conversationId}/chat`,
    request,
    callbacks
  );
};
