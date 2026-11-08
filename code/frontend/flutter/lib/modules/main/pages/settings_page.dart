import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../common/app_core.dart';
import '../../../common/services/api_error.dart';
import '../../../common/settings.dart';
import '../../authorization/providers/auth_provider.dart';
import '../../ai/providers/chat_provider.dart';
import '../../ai/pages/model_picker_page.dart';

/// 设置页：服务器连接 / AI 助手 / 外观 / 会话
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final TextEditingController _server;
  bool _testing = false;

  AppCore get core => context.read<AuthProvider>().core;

  @override
  void initState() {
    super.initState();
    _server = TextEditingController(text: core.settings.baseUrl);
  }

  String _normalize(String raw) {
    var url = raw.trim();
    if (url.isEmpty) return core.settings.baseUrl;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }
    while (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    return url;
  }

  Future<void> _saveAndTest() async {
    final url = _normalize(_server.text);
    _server.text = url;
    setState(() => _testing = true);
    core.updateBaseUrl(url);
    try {
      final probe = Dio(BaseOptions(
        baseUrl: url,
        connectTimeout: const Duration(seconds: 6),
        receiveTimeout: const Duration(seconds: 8),
      ));
      final resp = await probe.get('/authorization/auth/register-config');
      final ok = resp.statusCode == 200;
      if (!mounted) return;
      _toast(ok ? '连接成功，服务器工作正常' : '服务器响应异常（HTTP ${resp.statusCode}）');
    } catch (e) {
      if (!mounted) return;
      _toast('连接失败：${apiErrorMessage(e)}');
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _confirmClearSession() async {
    final scheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('清除登录信息'),
        content: const Text('将清除本地保存的令牌与用户信息，需要重新登录。确定继续吗？'),
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
            child: const Text('清除'),
          ),
        ],
      ),
    );
    if (ok == true && mounted) {
      core.session.clear();
      core.settings.setModelId(null);
      context.read<AuthProvider>().forceSignedOut();
      context.read<ChatProvider>().clearConversation();
      _toast('已清除登录信息');
    }
  }

  @override
  void dispose() {
    _server.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final settings = context.watch<AppSettings>();
    final chat = context.watch<ChatProvider>();
    final loggedIn = context.watch<AuthProvider>().user != null;

    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
        children: [
          _sectionTitle(context, '服务器连接'),
          Card(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('后端服务器地址',
                      style: TextStyle(
                          fontSize: 12.5, color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _server,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      hintText: '例如 http://192.168.1.10:6666',
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: _testing ? null : _saveAndTest,
                    icon: _testing
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.wifi_tethering_rounded, size: 17),
                    label: Text(_testing ? '正在测试…' : '保存并测试连接',
                        style: const TextStyle(fontSize: 13)),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),

          _sectionTitle(context, 'AI 助手'),
          Card(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('运行模式',
                                style: TextStyle(fontSize: 13.5)),
                            const SizedBox(height: 2),
                            Text(
                              settings.aiMode == AiMode.online
                                  ? '在线：调用服务器配置的大模型'
                                  : '本地：内置离线助手，无需联网',
                              style: TextStyle(
                                  fontSize: 11.5,
                                  color: scheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      SegmentedButton<AiMode>(
                        segments: const [
                          ButtonSegment(
                              value: AiMode.online,
                              label: Text('在线', style: TextStyle(fontSize: 12)),
                              icon: Icon(Icons.cloud_rounded, size: 15)),
                          ButtonSegment(
                              value: AiMode.local,
                              label: Text('本地', style: TextStyle(fontSize: 12)),
                              icon: Icon(Icons.phone_android_rounded,
                                  size: 15)),
                        ],
                        selected: {settings.aiMode},
                        onSelectionChanged: (s) =>
                            chat.switchMode(s.first),
                      ),
                    ],
                  ),
                ),
                const Divider(indent: 14, endIndent: 14),
                ListTile(
                  leading: const Icon(Icons.model_training_rounded, size: 20),
                  title:
                      const Text('对话模型', style: TextStyle(fontSize: 13.5)),
                  subtitle: Text(
                    loggedIn
                        ? (chat.currentModel?.label ?? '未选择')
                        : '登录后可选择服务器模型',
                    style: TextStyle(
                        fontSize: 11.5, color: scheme.onSurfaceVariant),
                  ),
                  trailing: Icon(Icons.chevron_right_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => const ModelPickerPage())),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          _sectionTitle(context, '外观'),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                children: [
                  Expanded(
                    child: Text('主题',
                        style: TextStyle(
                            fontSize: 13.5, color: scheme.onSurface.withValues(alpha: 1))),
                  ),
                  SegmentedButton<ThemeMode>(
                    segments: const [
                      ButtonSegment(
                          value: ThemeMode.system,
                          label: Text('自动', style: TextStyle(fontSize: 12))),
                      ButtonSegment(
                          value: ThemeMode.light,
                          label: Text('浅色', style: TextStyle(fontSize: 12))),
                      ButtonSegment(
                          value: ThemeMode.dark,
                          label: Text('深色', style: TextStyle(fontSize: 12))),
                    ],
                    selected: {settings.themeMode},
                    onSelectionChanged: (s) =>
                        settings.setThemeMode(s.first),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),

          _sectionTitle(context, '会话数据'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.delete_sweep_outlined, size: 20),
                  title: const Text('清空当前对话',
                      style: TextStyle(fontSize: 13.5)),
                  subtitle: Text('共 ${chat.messages.length} 条消息',
                      style: TextStyle(
                          fontSize: 11.5, color: scheme.onSurfaceVariant)),
                  onTap: chat.messages.isEmpty
                      ? null
                      : () {
                          chat.clearConversation();
                          _toast('已清空对话');
                        },
                ),
                const Divider(indent: 14, endIndent: 14),
                ListTile(
                  leading: Icon(Icons.logout_rounded,
                      size: 20, color: scheme.error),
                  title: Text('清除登录信息',
                      style: TextStyle(fontSize: 13.5, color: scheme.error)),
                  subtitle: Text('令牌失效时可用于重置登录状态',
                      style: TextStyle(
                          fontSize: 11.5, color: scheme.onSurfaceVariant)),
                  onTap: _confirmClearSession,
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          _sectionTitle(context, '关于'),
          const Card(
            child: ListTile(
              leading: Icon(Icons.info_outline_rounded, size: 20),
              title: Text('版本', style: TextStyle(fontSize: 13.5)),
              trailing: Text('CodeBiu Client 0.1.0',
                  style: TextStyle(fontSize: 12.5)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String text) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(text,
          style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              color: scheme.onSurfaceVariant,
              letterSpacing: 0.3)),
    );
  }
}
