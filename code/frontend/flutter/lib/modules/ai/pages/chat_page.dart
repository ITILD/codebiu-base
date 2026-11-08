import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../types/chat_message.dart';
import '../types/conversation.dart';
import '../../../common/settings.dart';
import '../../authorization/providers/auth_provider.dart';
import '../providers/chat_provider.dart';
import '../../agent/pages/agent_page.dart';
import '../../rag/pages/knowledge_page.dart';
import 'model_picker_page.dart';
import '../../authorization/pages/profile_page.dart';
import '../../main/pages/settings_page.dart';

/// AI 助手对话主页（应用唯一主界面）
///
/// 结构：左侧抽屉（会话历史 + 功能入口）；右上角头像菜单（历史/模型/我的/设置/退出）；
/// 新建对话时中间展示功能入口卡片（知识库等，后续新功能默认加在这里）。
class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  bool _nearBottom = true;
  int _lastCount = 0;
  int _lastLength = 0;
  String? _lastActiveId;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final pos = _scroll.position;
      _nearBottom =
          !pos.hasContentDimensions || pos.pixels >= pos.maxScrollExtent - 120;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ChatProvider>().loadModels();
    });
  }

  void _autoScroll(ChatProvider chat) {
    final last = chat.messages.isEmpty ? null : chat.messages.last;
    final length = last?.content.length ?? 0;
    final count = chat.messages.length;
    final switched = chat.active.id != _lastActiveId;
    if (!switched && count == _lastCount && length == _lastLength) return;
    _lastCount = count;
    _lastLength = length;
    _lastActiveId ??= chat.active.id;
    if (switched || _nearBottom || last?.role == ChatRole.user) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_scroll.hasClients) return;
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      });
    }
  }

  Future<void> _send([String? preset]) async {
    final chat = context.read<ChatProvider>();
    final text = (preset ?? _input.text).trim();
    if (text.isEmpty || chat.sending) return;
    if (preset == null) _input.clear();
    await chat.send(text);
  }

  void _showModeSheet(ChatProvider chat) {
    final scheme = Theme.of(context).colorScheme;
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: RadioGroup<AiMode>(
          groupValue: chat.isLocal ? AiMode.local : AiMode.online,
          onChanged: (v) {
            if (v != null) chat.switchMode(v);
            Navigator.of(ctx).pop();
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('AI 助手模式',
                      style: Theme.of(ctx)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.w700)),
                ),
              ),
              RadioListTile<AiMode>(
                value: AiMode.online,
                title: const Text('在线模式'),
                subtitle: const Text('调用服务器配置的大模型，能力更强',
                    style: TextStyle(fontSize: 12)),
                secondary: Icon(Icons.cloud_outlined, color: scheme.primary),
              ),
              RadioListTile<AiMode>(
                value: AiMode.local,
                title: const Text('本地模式'),
                subtitle: const Text('完全离线的内置助手，隐私安全、随时可用',
                    style: TextStyle(fontSize: 12)),
                secondary:
                    Icon(Icons.phone_android_rounded, color: scheme.primary),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmLogout() async {
    final scheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('退出登录'),
        content: const Text('确定要退出当前账号吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: scheme.error,
                minimumSize: const Size(64, 36)),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (ok == true && mounted) {
      await context.read<AuthProvider>().logout();
    }
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final chat = context.watch<ChatProvider>();
    final user = context.watch<AuthProvider>().user;
    _autoScroll(chat);

    final subtitle = chat.isLocal
        ? '本地 · 离线可用'
        : '在线 · ${chat.currentModel?.label ?? '未选择模型'}';

    return Scaffold(
      appBar: AppBar(
        leading: Builder(
          builder: (ctx) => IconButton(
            tooltip: '历史对话',
            icon: const Icon(Icons.menu_rounded, size: 22),
            onPressed: () => Scaffold.of(ctx).openDrawer(),
          ),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('AI 助手'),
            const SizedBox(height: 1),
            Text(subtitle,
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w400,
                    color: scheme.onSurfaceVariant)),
          ],
        ),
        actions: [
          // 模式快切
          InkWell(
            borderRadius: BorderRadius.circular(16),
            onTap: () => _showModeSheet(chat),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    chat.isLocal
                        ? Icons.phone_android_rounded
                        : Icons.cloud_rounded,
                    size: 14,
                    color: scheme.primary,
                  ),
                  const SizedBox(width: 4),
                  Text(chat.isLocal ? '本地' : '在线',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: scheme.primary)),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          // 头像即「更多」菜单
          PopupMenuButton<String>(
            tooltip: '更多',
            position: PopupMenuPosition.under,
            iconSize: 38,
            onSelected: (action) {
              switch (action) {
                case 'history':
                  Scaffold.of(context).openDrawer();
                  break;
                case 'model':
                  _push(const ModelPickerPage());
                  break;
                case 'profile':
                  _push(const ProfilePage());
                  break;
                case 'settings':
                  _push(const SettingsPage());
                  break;
                case 'logout':
                  _confirmLogout();
                  break;
              }
            },
            itemBuilder: (_) => const [
              PopupMenuItem(
                value: 'history',
                height: 44,
                child: Row(children: [
                  Icon(Icons.history_rounded, size: 18),
                  SizedBox(width: 10),
                  Text('历史记录', style: TextStyle(fontSize: 14)),
                ]),
              ),
              PopupMenuItem(
                value: 'model',
                height: 44,
                child: Row(children: [
                  Icon(Icons.model_training_rounded, size: 18),
                  SizedBox(width: 10),
                  Text('选择模型', style: TextStyle(fontSize: 14)),
                ]),
              ),
              PopupMenuItem(
                value: 'profile',
                height: 44,
                child: Row(children: [
                  Icon(Icons.person_outline_rounded, size: 18),
                  SizedBox(width: 10),
                  Text('我的', style: TextStyle(fontSize: 14)),
                ]),
              ),
              PopupMenuItem(
                value: 'settings',
                height: 44,
                child: Row(children: [
                  Icon(Icons.settings_outlined, size: 18),
                  SizedBox(width: 10),
                  Text('设置', style: TextStyle(fontSize: 14)),
                ]),
              ),
              PopupMenuDivider(),
              PopupMenuItem(
                value: 'logout',
                height: 44,
                child: Row(children: [
                  Icon(Icons.logout_rounded, size: 18),
                  SizedBox(width: 10),
                  Text('退出登录', style: TextStyle(fontSize: 14)),
                ]),
              ),
            ],
            icon: user == null
                ? CircleAvatar(
                    radius: 15,
                    backgroundColor: scheme.primary.withValues(alpha: 0.15),
                    child: Icon(Icons.person_rounded,
                        size: 17, color: scheme.primary),
                  )
                : UserAvatar(user: user, size: 32, radius: 16),
          ),
          const SizedBox(width: 4),
        ],
      ),
      drawer: _HistoryDrawer(onClose: () => Navigator.of(context).pop()),
      body: Column(
        children: [
          const Divider(height: 1),
          Expanded(
            child: chat.messages.isEmpty
                ? _EmptyView(onPick: (s) => _send(s))
                : ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
                    itemCount: chat.messages.length,
                    itemBuilder: (_, i) => _Bubble(
                      message: chat.messages[i],
                      onRetry: () => context.read<ChatProvider>().retryLast(),
                    ),
                  ),
          ),
          const Divider(height: 1),
          _InputBar(
            controller: _input,
            sending: chat.sending,
            onSend: () => _send(),
          ),
        ],
      ),
    );
  }

  void _push(Widget page) {
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));
  }
}

/// 左侧抽屉：会话历史 + 功能入口
class _HistoryDrawer extends StatelessWidget {
  const _HistoryDrawer({required this.onClose});

  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final chat = context.watch<ChatProvider>();
    final user = context.watch<AuthProvider>().user;

    void jump(Widget page) {
      onClose();
      Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => page));
    }

    return Drawer(
      width: 300,
      backgroundColor: scheme.surface,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 用户头部
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 12, 10),
              child: Row(
                children: [
                  if (user != null)
                    UserAvatar(user: user, size: 38, radius: 12)
                  else
                    CircleAvatar(
                      radius: 19,
                      backgroundColor:
                          scheme.primary.withValues(alpha: 0.15),
                      child: Icon(Icons.person_rounded,
                          size: 20, color: scheme.primary),
                    ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(user?.displayName ?? '未登录',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 15, fontWeight: FontWeight.w700)),
                        if (user != null)
                          Text('@${user.username}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 11,
                                  color: scheme.onSurfaceVariant)),
                      ],
                    ),
                  ),
                  IconButton(
                    tooltip: '我的',
                    icon: Icon(Icons.chevron_right_rounded,
                        size: 20, color: scheme.onSurfaceVariant),
                    onPressed: () => jump(const ProfilePage()),
                  ),
                ],
              ),
            ),

            // 新建对话
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: FilledButton.tonalIcon(
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(42),
                  alignment: Alignment.centerLeft,
                ),
                onPressed: () {
                  context.read<ChatProvider>().newConversation();
                  onClose();
                },
                icon: const Icon(Icons.add_rounded, size: 18),
                label: const Text('新建对话',
                    style: TextStyle(fontSize: 13.5)),
              ),
            ),
            const SizedBox(height: 6),

            Padding(
              padding: const EdgeInsets.fromLTRB(20, 6, 20, 4),
              child: Row(
                children: [
                  Text('历史对话',
                      style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant)),
                  const Spacer(),
                  Text('${chat.conversations.length}',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant)),
                ],
              ),
            ),
            const Divider(indent: 16, endIndent: 16, height: 4),

            // 历史列表
            Expanded(
              child: chat.conversations.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Text('暂无历史对话\n发送第一条消息后自动记录',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                                fontSize: 12,
                                color: scheme.onSurfaceVariant)),
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 6),
                      itemCount: chat.conversations.length,
                      itemBuilder: (_, i) {
                        final c = chat.conversations[i];
                        final current = c.id == chat.active.id;
                        return _historyTile(context, c, current, chat);
                      },
                    ),
            ),

            const Divider(height: 1, indent: 16, endIndent: 16),

            // 功能入口
            ListTile(
              dense: true,
              leading: const Icon(Icons.auto_awesome_rounded, size: 20),
              title: const Text('智能体配置', style: TextStyle(fontSize: 13.5)),
              trailing: Icon(Icons.chevron_right_rounded,
                  size: 17, color: scheme.onSurfaceVariant),
              onTap: () => jump(const AgentPage()),
            ),
            ListTile(
              dense: true,
              leading: const Icon(Icons.menu_book_outlined, size: 20),
              title: const Text('知识库', style: TextStyle(fontSize: 13.5)),
              trailing: Icon(Icons.chevron_right_rounded,
                  size: 17, color: scheme.onSurfaceVariant),
              onTap: () => jump(const KnowledgePage()),
            ),
          ],
        ),
      ),
    );
  }

  Widget _historyTile(
      BuildContext context, Conversation c, bool current, ChatProvider chat) {
    final scheme = Theme.of(context).colorScheme;
    final time = '${c.updatedAt.month.toString().padLeft(2, '0')}-'
        '${c.updatedAt.day.toString().padLeft(2, '0')} '
        '${c.updatedAt.hour.toString().padLeft(2, '0')}:'
        '${c.updatedAt.minute.toString().padLeft(2, '0')}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Material(
        color: current
            ? scheme.primary.withValues(alpha: 0.08)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        child: ListTile(
          dense: true,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          title: Text(c.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: 13.5,
                  fontWeight: current ? FontWeight.w600 : FontWeight.w500)),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
                '$time · ${c.messages.length} 条',
                style: TextStyle(
                    fontSize: 11, color: scheme.onSurfaceVariant)),
          ),
          onTap: () {
            context.read<ChatProvider>().switchTo(c.id);
            onClose();
          },
          trailing: IconButton(
            tooltip: '删除对话',
            visualDensity: VisualDensity.compact,
            icon: Icon(Icons.delete_outline_rounded,
                size: 17, color: scheme.onSurfaceVariant),
            onPressed: () {
              context.read<ChatProvider>().removeConversation(c.id);
            },
          ),
        ),
      ),
    );
  }
}

/// 空状态（新建对话）：功能入口卡片 + 建议问题
///
/// 基线约定：后续新功能默认入口都注册在这里（_features 列表）。
class _EmptyView extends StatelessWidget {
  const _EmptyView({required this.onPick});

  final ValueChanged<String> onPick;

  static const _features = <(IconData, String, String, String)>[
    (Icons.menu_book_outlined, '知识库', '管理与上传文档', 'kb'),
    // 后续新功能入口在此追加：(图标, 名称, 说明, 动作key)
  ];

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final chat = context.watch<ChatProvider>();
    final local = chat.isLocal;
    final suggestions = local
        ? const ['现在几点了？', '计算 (128+64)/8*2.5', '讲个笑话', '帮助']
        : const [
            '你好，介绍一下你自己',
            '用通俗的语言解释一下量子纠缠',
            '帮我写一首关于春天的短诗',
            '推荐三本管理学经典书籍',
          ];

    void onFeature(String key) {
      switch (key) {
        case 'kb':
          Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => const KnowledgePage()));
          break;
      }
    }

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.smart_toy_rounded,
                  size: 36, color: scheme.primary),
            ),
            const SizedBox(height: 16),
            Text('你好，我是 CodeBiu AI 助手',
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              local ? '当前为本地模式：离线可用，擅长计算与查询' : '当前为在线模式：由服务器大模型提供回答',
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 20),
            // 功能入口卡片（仅新建对话时可见）
            if (_features.isNotEmpty)
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.center,
                children: [
                  for (final (icon, name, desc, key) in _features)
                    _FeatureCard(
                      icon: icon,
                      name: name,
                      description: desc,
                      onTap: () => onFeature(key),
                    ),
                ],
              ),
            const SizedBox(height: 20),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              alignment: WrapAlignment.center,
              children: [
                for (final s in suggestions)
                  ActionChip(
                    label: Text(s, style: const TextStyle(fontSize: 12.5)),
                    onPressed: () => onPick(s),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// 功能入口卡片
class _FeatureCard extends StatelessWidget {
  const _FeatureCard({
    required this.icon,
    required this.name,
    required this.description,
    required this.onTap,
  });

  final IconData icon;
  final String name;
  final String description;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: onTap,
      child: Container(
        width: 150,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 19, color: scheme.primary),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name,
                      style: const TextStyle(
                          fontSize: 13.5, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(description,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 消息气泡
class _Bubble extends StatelessWidget {
  const _Bubble({required this.message, required this.onRetry});

  final ChatMessage message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isUser = message.role == ChatRole.user;

    final bubble = Container(
      constraints: const BoxConstraints(maxWidth: 320),
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 10),
      decoration: BoxDecoration(
        color: isUser ? scheme.primary : scheme.surface,
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(14),
          topRight: const Radius.circular(14),
          bottomLeft: Radius.circular(isUser ? 14 : 4),
          bottomRight: Radius.circular(isUser ? 4 : 14),
        ),
        border: isUser
            ? null
            : Border.all(color: scheme.outlineVariant.withValues(alpha: 0.6)),
      ),
      child: _content(context, scheme),
    );

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: GestureDetector(
          onLongPress: () {
            if (message.content.isEmpty) return;
            Clipboard.setData(ClipboardData(text: message.content));
            ScaffoldMessenger.of(context)
              ..hideCurrentSnackBar()
              ..showSnackBar(const SnackBar(content: Text('已复制到剪贴板')));
          },
          child: bubble,
        ),
      ),
    );
  }

  Widget _content(BuildContext context, ColorScheme scheme) {
    final isUser = message.role == ChatRole.user;
    if (message.isError && message.content.isEmpty) {
      // 纯错误占位
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline_rounded, size: 15, color: scheme.error),
              const SizedBox(width: 5),
              Flexible(
                child: Text(
                  message.error ?? '请求失败',
                  style: TextStyle(fontSize: 13, color: scheme.error),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 30,
            child: OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 14),
              label: const Text('重试', style: TextStyle(fontSize: 12)),
            ),
          ),
        ],
      );
    }

    final text = message.streaming && message.content.isNotEmpty
        ? '${message.content}▍'
        : message.content;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (message.content.isEmpty && message.streaming)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: scheme.primary),
              ),
              const SizedBox(width: 8),
              Text('思考中…',
                  style: TextStyle(
                      fontSize: 12.5, color: scheme.onSurfaceVariant)),
            ],
          )
        else
          SelectableText(
            text,
            style: TextStyle(
              fontSize: 14,
              height: 1.5,
              color: isUser ? scheme.onPrimary : scheme.onSurface,
            ),
          ),
        if (message.isError) ...[
          const SizedBox(height: 6),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.warning_amber_rounded, size: 13, color: scheme.error),
              const SizedBox(width: 4),
              Flexible(
                child: Text(message.error ?? '',
                    style: TextStyle(fontSize: 11.5, color: scheme.error)),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: onRetry,
                child: Text('重试',
                    style: TextStyle(
                        fontSize: 11.5,
                        color: scheme.primary,
                        fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

/// 底部输入栏：回车发送 / Shift+回车换行 / 手机键盘「发送」键发送
class _InputBar extends StatefulWidget {
  const _InputBar({
    required this.controller,
    required this.sending,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;

  @override
  State<_InputBar> createState() => _InputBarState();
}

class _InputBarState extends State<_InputBar> {
  final _keyboardFocus = FocusNode();

  @override
  void dispose() {
    _keyboardFocus.dispose();
    super.dispose();
  }

  /// 硬件键盘：Enter 发送并拦截换行；Shift+Enter 放行换行
  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is KeyDownEvent &&
        (event.logicalKey == LogicalKeyboardKey.enter ||
            event.logicalKey == LogicalKeyboardKey.numpadEnter)) {
      if (HardwareKeyboard.instance.isShiftPressed) {
        return KeyEventResult.ignored; // 插入换行
      }
      widget.onSend();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
        color: scheme.surface,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Focus(
                focusNode: _keyboardFocus,
                onKeyEvent: _onKey,
                skipTraversal: true,
                canRequestFocus: false,
                child: TextField(
                  controller: widget.controller,
                  enabled: !widget.sending,
                  minLines: 1,
                  maxLines: 4,
                  // 软键盘显示「发送」动作键；硬件键盘的 Enter 由 Focus 处理
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => widget.onSend(),
                  decoration: InputDecoration(
                    hintText: '输入消息…',
                    fillColor: Theme.of(context).scaffoldBackgroundColor,
                    filled: true,
                    contentPadding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: widget.controller,
              builder: (context, value, _) {
                final canSend = value.text.trim().isNotEmpty && !widget.sending;
                return IconButton.filled(
                  style: IconButton.styleFrom(
                    backgroundColor: canSend
                        ? scheme.primary
                        : scheme.primary.withValues(alpha: 0.35),
                    foregroundColor: scheme.onPrimary,
                  ),
                  onPressed: canSend ? widget.onSend : null,
                  icon: widget.sending
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.arrow_upward_rounded, size: 20),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
