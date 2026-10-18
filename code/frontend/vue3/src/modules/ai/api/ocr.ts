/**
 * OCR相关的API接口
 */
import type { Language, OcrResponse } from '../types/ocr';
import { http_base_server } from '@/common/api/http';

/** 获取OCR支持的语言列表 */
export const listOcrLanguages = async () => {
 return http_base_server.get<Language[]>('/ai/ocr/languages');
};

/** 对图片执行OCR识别(在线外部服务, 语言自动检测) */
export const recognizeText = async (formData: FormData) => {
  return http_base_server.post<OcrResponse>('/ai/ocr/all', formData);
}
