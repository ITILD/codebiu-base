/**
 * 后台布局/骨架屏/错误边界词条(三元数组: [zh, ja, en])
 * 由 language.ts 合并进全局语言对照表
 */
export const layoutKeys: Record<string, string[]> = {
  err_title: ['页面出了点问题', 'ページで問題が発生しました', 'Something went wrong'],
  err_desc: [
    '可以重试，或复制错误信息反馈给管理员。',
    '再試行するか、エラー情報をコピーして管理者に共有してください。',
    'Retry, or copy the error details to report it.',
  ],
  err_retry: ['重试', '再試行', 'Retry'],
  err_copy: ['复制错误信息', 'エラー情報をコピー', 'Copy details'],
  err_copied: ['已复制', 'コピーしました', 'Copied'],
  err_detail: ['错误详情', 'エラー詳細', 'Error details'],
  loading: ['加载中', '読み込み中', 'Loading'],
  skip_to_content: ['跳到主内容', 'メインコンテンツへ', 'Skip to content'],
}
