import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../types/user.dart';
import '../providers/auth_provider.dart';
import 'password_page.dart';
import 'profile_edit_page.dart';
import '../../main/pages/settings_page.dart';

/// 我的：用户信息 + 账号操作
class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final user = context.watch<AuthProvider>().user;
    if (user == null) return const SizedBox.shrink();

    final created = user.createdAt == null
        ? null
        : '${user.createdAt!.year}-${user.createdAt!.month.toString().padLeft(2, '0')}-${user.createdAt!.day.toString().padLeft(2, '0')}';

    return Scaffold(
      appBar: AppBar(title: const Text('我的')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 24),
        children: [
          // 用户卡片
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  UserAvatar(user: user, size: 56, radius: 18),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(user.displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 17, fontWeight: FontWeight.w700)),
                        const SizedBox(height: 3),
                        Text('@${user.username}',
                            style: TextStyle(
                                fontSize: 12.5,
                                color: scheme.onSurfaceVariant)),
                        if (user.email != null) ...[
                          const SizedBox(height: 3),
                          Text(user.email!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 12,
                                  color: scheme.onSurfaceVariant)),
                        ],
                      ],
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: (user.isActive ? scheme.primary : scheme.error)
                          .withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      user.isActive ? '正常' : '禁用',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color:
                            user.isActive ? scheme.primary : scheme.error,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),

          // 账号信息
          _sectionTitle(context, '账号信息'),
          Card(
            child: Column(
              children: [
                _infoTile(context, Icons.mail_outline_rounded, '邮箱',
                    user.email ?? '未设置'),
                const Divider(indent: 14, endIndent: 14),
                _infoTile(context, Icons.phone_outlined, '手机号',
                    user.phone ?? '未设置'),
                const Divider(indent: 14, endIndent: 14),
                _infoTile(context, Icons.calendar_today_outlined, '注册时间',
                    created ?? '未知'),
                const Divider(indent: 14, endIndent: 14),
                _infoTile(context, Icons.verified_user_outlined, '用户 ID',
                    user.id, isMono: true),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // 快捷操作
          _sectionTitle(context, '账号管理'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.edit_outlined, size: 20),
                  title: const Text('编辑资料',
                      style: TextStyle(fontSize: 14)),
                  trailing: Icon(Icons.chevron_right_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => const ProfileEditPage())),
                ),
                const Divider(indent: 14, endIndent: 14),
                ListTile(
                  leading: const Icon(Icons.password_outlined, size: 20),
                  title: const Text('修改密码',
                      style: TextStyle(fontSize: 14)),
                  trailing: Icon(Icons.chevron_right_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => const PasswordPage())),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // 应用
          _sectionTitle(context, '应用'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.settings_outlined, size: 20),
                  title: const Text('设置',
                      style: TextStyle(fontSize: 14)),
                  subtitle: const Text('服务器地址 · AI 模式 · 外观',
                      style: TextStyle(fontSize: 11.5)),
                  trailing: Icon(Icons.chevron_right_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                      builder: (_) => const SettingsPage())),
                ),
                const Divider(indent: 14, endIndent: 14),
                ListTile(
                  leading: const Icon(Icons.info_outline_rounded, size: 20),
                  title: const Text('关于 CodeBiu',
                      style: TextStyle(fontSize: 14)),
                  trailing: Icon(Icons.chevron_right_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onTap: () {
                    showAboutDialog(
                      context: context,
                      applicationName: 'CodeBiu 客户端',
                      applicationVersion: '0.1.0',
                      applicationIcon: Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(
                          color: scheme.primary,
                          borderRadius: BorderRadius.circular(11),
                        ),
                        child: Icon(Icons.smart_toy_rounded,
                            color: scheme.onPrimary, size: 22),
                      ),
                      children: const [
                        Text('手机与 PC 桌面同构客户端，'
                            '内置在线 AI 助手（服务器模型）与本地离线助手。'),
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),

          // 退出登录
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              foregroundColor: scheme.error,
              side: BorderSide(color: scheme.error.withValues(alpha: 0.5)),
              minimumSize: const Size.fromHeight(44),
            ),
            onPressed: () => _confirmLogout(context),
            icon: const Icon(Icons.logout_rounded, size: 18),
            label: const Text('退出登录'),
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

  Widget _infoTile(BuildContext context, IconData icon, String label,
      String value,
      {bool isMono = false}) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      child: Row(
        children: [
          Icon(icon, size: 18, color: scheme.onSurfaceVariant),
          const SizedBox(width: 10),
          Text(label,
              style: const TextStyle(fontSize: 13.5)),
          const Spacer(),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
              style: TextStyle(
                fontSize: 13,
                color: scheme.onSurfaceVariant,
                fontFamily: isMono ? 'monospace' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmLogout(BuildContext context) async {
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
                minimumSize: Size(64, 36)),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (ok == true && context.mounted) {
      await context.read<AuthProvider>().logout();
    }
  }
}

/// 用户头像：有地址则加载图片，否则取首字符
class UserAvatar extends StatelessWidget {
  const UserAvatar({
    super.key,
    required this.user,
    this.size = 40,
    this.radius = 13,
  });

  final User user;
  final double size;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final initial = user.displayName.isEmpty
        ? '?'
        : user.displayName.characters.first.toUpperCase();
    Widget child;
    if (user.avatar != null && user.avatar!.startsWith('http')) {
      child = ClipRRect(
        borderRadius: BorderRadius.circular(radius),
        child: Image.network(
          user.avatar!,
          width: size,
          height: size,
          fit: BoxFit.cover,
          errorBuilder: (_, _, _) => _initial(scheme, initial),
        ),
      );
      return SizedBox(width: size, height: size, child: child);
    }
    return _initial(scheme, initial);
  }

  Widget _initial(ColorScheme scheme, String initial) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(radius),
      ),
      child: Text(
        initial,
        style: TextStyle(
          fontSize: size * 0.42,
          fontWeight: FontWeight.w700,
          color: scheme.primary,
        ),
      ),
    );
  }
}
