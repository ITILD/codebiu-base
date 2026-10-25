/**
 * AI 助手(后台配置 + 悬浮入口 + 内页导航)词条
 * 三元数组按 [zh, ja, en] 下标对齐, 由 language.ts 合并进全局语言对照表
 */
export const assistantKeys: Record<string, string[]> = {
  // ===== 后台: AI 助手配置页 =====
  asst_title: ['AI 助手配置', 'AIアシスタント設定', 'AI Assistant Settings'],
  asst_subtitle: [
    '助手的展示形态、默认对话参数与悬浮入口',
    '表示形式・既定の会話設定・フローティング入口',
    'Appearance, default chat options and floating entry',
  ],
  asst_display: ['展示形态', '表示形式', 'Appearance'],
  asst_float_enable: ['启用悬浮助手', 'フローティングアシスタントを有効化', 'Enable floating assistant'],
  asst_float_enable_hint: [
    '关闭后仅保留页面内 AI 助手入口',
    'オフにするとページ内の入口のみになります',
    'When off, only the in-page assistant entry remains',
  ],
  asst_auto_open: ['进入页面自动弹开', 'ページ表示時に自動で開く', 'Auto open on page load'],
  asst_auto_open_hint: [
    '每个浏览器会话首次加载时异步展开一次',
    'ブラウザセッションごとに初回のみ遅延展開します',
    'Lazily opens once on the first load of each browser session',
  ],
  asst_position: ['悬浮按钮位置', 'ボタンの位置', 'Button position'],
  asst_position_right: ['右下', '右下', 'Bottom right'],
  asst_position_left: ['左下', '左下', 'Bottom left'],
  asst_defaults: ['默认对话参数', '既定の会話設定', 'Default chat options'],
  asst_default_agent: ['默认助手', '既定のアシスタント', 'Default assistant'],
  asst_no_agent: ['仅知识库（不绑定助手）', 'ナレッジのみ（アシスタントなし）', 'Knowledge base only'],
  asst_default_kb: ['默认知识库', '既定のナレッジベース', 'Default knowledge bases'],
  asst_deep_thinking: ['默认深度思考', '既定の深い思考', 'Default deep thinking'],
  asst_websearch: ['默认联网搜索', '既定のウェブ検索', 'Default web search'],
  asst_welcome: ['欢迎语与快捷提问', '挨拶とクイック質問', 'Greeting and quick prompts'],
  asst_greeting: ['欢迎语', '挨拶文', 'Greeting'],
  asst_greeting_ph: ['留空则使用默认欢迎语', '空欄の場合は既定の挨拶を使用', 'Leave blank to use the default greeting'],
  asst_suggestions: ['快捷提问', 'クイック質問', 'Quick prompts'],
  asst_suggestion_ph: ['输入一条快捷提问', 'クイック質問を入力', 'Enter a quick prompt'],
  asst_add_suggestion: ['添加快捷提问', 'クイック質問を追加', 'Add prompt'],
  asst_remove: ['移除', '削除', 'Remove'],
  asst_entries: ['快捷入口', 'ショートカット', 'Shortcuts'],
  asst_entry_chat: ['打开 AI 助手', 'AIアシスタントを開く', 'Open AI Assistant'],
  asst_entry_chat_desc: [
    '最终使用界面：知识库问答与助手对话',
    '最終利用画面：ナレッジQ&Aとアシスタント会話',
    'End-user surface: knowledge Q&A and assistant chat',
  ],
  asst_entry_kb: ['知识库管理', 'ナレッジベース管理', 'Knowledge bases'],
  asst_entry_kb_desc: [
    '文档上传、解析与成员授权',
    '文書のアップロード・解析・権限',
    'Upload, parse and share documents',
  ],
  asst_entry_agent: ['智能体编排', 'エージェント編成', 'Agent orchestration'],
  asst_entry_agent_desc: [
    '助手与技能的注册管理',
    'アシスタントとスキルの管理',
    'Register assistants and skills',
  ],
  asst_save: ['保存配置', '設定を保存', 'Save'],
  asst_reset: ['恢复默认', '既定に戻す', 'Reset'],
  asst_saved: ['配置已保存', '設定を保存しました', 'Settings saved'],
  asst_reset_done: ['已恢复默认配置', '既定に戻しました', 'Reset to defaults'],
  asst_model_hint: [
    '模型选择与个人绑定请在「设置 · 模型」中调整',
    'モデルと個人設定は「設定 · モデル」で変更してください',
    'Adjust models and personal binding in Settings · Models',
  ],

  // ===== AI 助手内页导航 =====
  asst_nav_chat: ['AI 助手', 'AIアシスタント', 'AI Assistant'],
  asst_nav_kb: ['知识库管理', 'ナレッジベース管理', 'Knowledge bases'],
  asst_nav_agent: ['智能体编排', 'エージェント編成', 'Agent orchestration'],

  // ===== 悬浮助手 =====
  asst_widget_title: ['AI 助手', 'AIアシスタント', 'AI Assistant'],
  asst_new_chat: ['新对话', '新しい会話', 'New chat'],
  asst_expand: ['全屏', '全画面', 'Full screen'],
  asst_close: ['收起', '閉じる', 'Close'],
  asst_empty: [
    '问我任何问题，我会结合知识库与助手技能回答',
    '何でも聞いてください。ナレッジとスキルを活用して回答します',
    'Ask me anything — I use your knowledge base and skills',
  ],
  asst_placeholder: ['输入问题，Enter 发送', '質問を入力（Enterで送信）', 'Type a question, Enter to send'],
  asst_send: ['发送', '送信', 'Send'],
  asst_stop: ['停止', '停止', 'Stop'],
  asst_failed: ['发送失败，请重试', '送信に失敗しました。再試行してください', 'Failed to send, please retry'],
  asst_stopped: ['（已停止生成）', '（生成を停止しました）', '(Generation stopped)'],
  asst_no_reply: ['（未收到回复，请重试）', '（応答がありません。再試行してください）', '(No reply, please retry)'],
  asst_conversation_failed: ['创建对话失败', '会話の作成に失敗しました', 'Failed to create conversation'],
  asst_settings: ['助手设置', 'アシスタント設定', 'Assistant settings'],
  asst_only_kb: ['仅知识库', 'ナレッジのみ', 'Knowledge only'],
}
