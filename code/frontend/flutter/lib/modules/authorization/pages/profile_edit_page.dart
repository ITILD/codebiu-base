import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../common/services/api_error.dart';
import '../providers/auth_provider.dart';
import 'profile_page.dart';

/// 编辑资料页
class ProfileEditPage extends StatefulWidget {
  const ProfileEditPage({super.key});

  @override
  State<ProfileEditPage> createState() => _ProfileEditPageState();
}

class _ProfileEditPageState extends State<ProfileEditPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nickname;
  late final TextEditingController _email;
  late final TextEditingController _phone;
  late final TextEditingController _avatar;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final user = context.read<AuthProvider>().user;
    _nickname = TextEditingController(text: user?.nickname ?? '');
    _email = TextEditingController(text: user?.email ?? '');
    _phone = TextEditingController(text: user?.phone ?? '');
    _avatar = TextEditingController(text: user?.avatar ?? '');
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      await context.read<AuthProvider>().updateProfile(
            nickname: _nickname.text.trim(),
            email: _email.text.trim(),
            phone: _phone.text.trim(),
            avatar: _avatar.text.trim(),
          );
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(const SnackBar(content: Text('资料已更新')));
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _nickname.dispose();
    _email.dispose();
    _phone.dispose();
    _avatar.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final user = context.watch<AuthProvider>().user;
    return Scaffold(
      appBar: AppBar(title: const Text('编辑资料')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (user != null) ...[
                Center(
                  child: UserAvatar(user: user, size: 72, radius: 22),
                ),
                const SizedBox(height: 6),
                Center(
                  child: Text('@${user.username}',
                      style: TextStyle(
                          fontSize: 12.5, color: scheme.onSurfaceVariant)),
                ),
                const SizedBox(height: 18),
              ],
              TextFormField(
                controller: _nickname,
                decoration: const InputDecoration(
                  labelText: '昵称',
                  prefixIcon: Icon(Icons.badge_outlined),
                  helperText: '留空则展示用户名',
                ),
                validator: (v) =>
                    (v != null && v.trim().length > 50) ? '昵称不能超过 50 个字符' : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(
                  labelText: '邮箱',
                  prefixIcon: Icon(Icons.mail_outline_rounded),
                ),
                validator: (v) {
                  final s = v?.trim() ?? '';
                  if (s.isEmpty) return null;
                  if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(s)) {
                    return '邮箱格式不正确';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: '手机号',
                  prefixIcon: Icon(Icons.phone_outlined),
                ),
                validator: (v) {
                  final s = v?.trim() ?? '';
                  if (s.isEmpty) return null;
                  if (!RegExp(r'^\+?\d{5,20}$').hasMatch(s)) {
                    return '手机号格式不正确';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _avatar,
                decoration: const InputDecoration(
                  labelText: '头像地址',
                  prefixIcon: Icon(Icons.image_outlined),
                  helperText: '选填，图片 URL（http/https）',
                ),
                validator: (v) {
                  final s = v?.trim() ?? '';
                  if (s.isEmpty) return null;
                  if (!s.startsWith('http://') && !s.startsWith('https://')) {
                    return '请输入 http(s) 图片地址';
                  }
                  if (s.length > 255) return '地址过长';
                  return null;
                },
              ),
              const SizedBox(height: 26),
              FilledButton(
                onPressed: _saving ? null : _save,
                child: _saving
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('保存修改'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
