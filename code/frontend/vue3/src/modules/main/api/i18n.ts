// src/modules/main/api/i18n.ts
// 多语言词条覆盖接口(对应后端 /i18n): 覆盖表 CRUD + 导出/导入
import { http_base_server } from '@/common/api/http';
import type {
  I18nEntry,
  I18nImportResult,
  I18nOverride,
  I18nOverrideItem,
} from '../types/i18n';

/** 获取全部词条覆盖记录 */
export const listI18nOverrides = () => {
  return http_base_server.get<I18nOverride[]>('/i18n/overrides');
};

/** 批量保存词条覆盖(单条保存同样走此接口) */
export const saveI18nOverrides = (items: I18nOverrideItem[]) => {
  return http_base_server.put<{ count: number }>('/i18n/overrides', { items });
};

/** 删除单条词条覆盖 */
export const deleteI18nOverride = (key: string) => {
  return http_base_server.delete<void>(`/i18n/overrides/${encodeURIComponent(key)}`);
};

/** 导出全部词条覆盖(不含时间戳) */
export const exportI18nEntries = () => {
  return http_base_server.get<{ items: I18nEntry[] }>('/i18n/export');
};

/** 导入词条(overwrite=true 时覆盖同名词条) */
export const importI18nEntries = (items: I18nEntry[], overwrite?: boolean) => {
  return http_base_server.post<I18nImportResult>('/i18n/import', { items, overwrite });
};
