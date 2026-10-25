// 多语言词条后台管理类型(对应后端 /i18n 接口契约)

/** 词条覆盖记录(后台维护的运行时覆盖表) */
export interface I18nOverride {
  key: string
  zh: string
  ja: string
  en: string
  /** 最近更新时间(ISO) */
  updated_at: string
}

/** 批量保存/导入的单词条(未提供的语言保持原值) */
export interface I18nOverrideItem {
  key: string
  zh?: string
  ja?: string
  en?: string
}

/** 导出/导入使用的完整词条 */
export interface I18nEntry {
  key: string
  zh: string
  ja: string
  en: string
}

/** 导入结果 */
export interface I18nImportResult {
  /** 成功导入条数 */
  count: number
  /** 被跳过的键名(未开覆盖且已存在) */
  skipped: string[]
}
