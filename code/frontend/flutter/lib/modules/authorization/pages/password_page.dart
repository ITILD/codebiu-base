import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../common/services/api_error.dart';
import '../providers/auth_provider.dart';

/// 修改密码页
class PasswordPage extends StatefulWidget {
  const PasswordPage({super.key});

  @override
  State<PasswordPage> createState() => _PasswordPageState();
}

class _PasswordPageState extends State<PasswordPage> {
  final _formKey = GlobalKey<FormState>();
  final _old = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  final bool _obscure = true;
  bool _saving = false;

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      await context
          .read<AuthProvider>()
          .core
          .auth
          .changePassword(_old.text, _new.text);
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(const SnackBar(content: Text('密码修改成功')));
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
    _old.dispose();
    _new.dispose();
    _confirm.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('修改密码')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _old,
                obscureText: _obscure,
                decoration: const InputDecoration(
                  labelText: '当前密码',
                  prefixIcon: Icon(Icons.lock_outline_rounded),
                ),
                validator: (v) =>
                    (v == null || v.isEmpty) ? '请输入当前密码' : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _new,
                obscureText: _obscure,
                decoration: const InputDecoration(
                  labelText: '新密码',
                  prefixIcon: Icon(Icons.key_outlined),
                  helperText: '至少 6 位，且不能与当前密码相同',
                ),
                validator: (v) {
                  if (v == null || v.isEmpty) return '请输入新密码';
                  if (v.length < 6) return '密码至少 6 位字符';
                  if (v == _old.text) return '新密码不能与当前密码相同';
                  return null;
                },
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _confirm,
                obscureText: _obscure,
                onFieldSubmitted: (_) => _save(),
                decoration: const InputDecoration(
                  labelText: '确认新密码',
                  prefixIcon: Icon(Icons.lock_reset_outlined),
                ),
                validator: (v) {
                  if (v == null || v.isEmpty) return '请再次输入新密码';
                  if (v != _new.text) return '两次输入的密码不一致';
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
                    : const Text('确认修改'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
