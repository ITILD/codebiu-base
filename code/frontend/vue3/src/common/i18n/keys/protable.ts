/**
 * ProTable 通用表格组件词条(三元数组: [zh, ja, en])
 * 由 language.ts 合并进全局语言对照表
 */
export const protableKeys: Record<string, string[]> = {
  pt_col_settings: ['列设置', '列設定', 'Columns'],
  pt_col_hint: ['勾选需要显示的列，可调整顺序', '表示する列にチェック、順序も調整可能', 'Pick visible columns and reorder'],
  pt_density: ['密度', '密度', 'Density'],
  pt_density_default: ['默认', '標準', 'Default'],
  pt_density_medium: ['中等', '中', 'Medium'],
  pt_density_small: ['紧凑', 'コンパクト', 'Compact'],
  pt_reset: ['重置', 'リセット', 'Reset'],
  pt_actions: ['操作', '操作', 'Actions'],
  pt_selected: ['已选 {n} 项', '{n} 件選択中', '{n} selected'],
  pt_clear_selection: ['取消选择', '選択解除', 'Clear selection'],
  pt_edit: ['编辑', '編集', 'Edit'],
  pt_save: ['保存', '保存', 'Save'],
  pt_cancel: ['取消', 'キャンセル', 'Cancel'],
  pt_empty: ['暂无数据', 'データなし', 'No data'],
  pt_total: ['共 {n} 条', '全 {n} 件', '{n} items'],
  pt_move_up: ['上移', '上へ', 'Move up'],
  pt_move_down: ['下移', '下へ', 'Move down'],
  pt_more: ['更多', 'その他', 'More'],
  pt_card_view: ['卡片视图', 'カード表示', 'Card view'],
  pt_table_view: ['表格视图', 'テーブル表示', 'Table view'],
}
