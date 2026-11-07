import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/services/api_error.dart';
import '../../providers/auth_provider.dart';

/// 注册页
class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _nickname = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _code = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  bool _sendingCode = false;
  bool _emailVerify = false;
  int _codeCountdown = 0;

  @override
  void initState() {
    super.initState();
    _loadConfig();
  }

  Future<void> _loadConfig() async {
    try {
      final need = await context
          .read<AuthProvider>()
          .core
          .auth
          .registerNeedsEmailVerify();
      if (mounted) setState(() => _emailVerify = need);
    } catch (_) {
      // 拉取失败按不需要验证码处理
    }
  }

  Future<void> _sendCode() async {
    final email = _email.text.trim();
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
      _toast('请先输入正确的邮箱地址');
      return;
    }
    setState(() => _sendingCode = true);
    try {
      await context
          .read<AuthProvider>()
          .core
          .auth
          .sendRegisterCode(email);
      if (!mounted) return;
      _toast('验证码已发送，请查收邮箱');
      setState(() => _codeCountdown = 60);
      Future.doWhile(() async {
        await Future<void>.delayed(const Duration(seconds: 1));
        if (!mounted) return false;
        setState(() => _codeCountdown--);
        return _codeCountdown > 0;
      });
    } catch (e) {
      if (mounted) _toast(apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _sendingCode = false);
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      await context.read<AuthProvider>().register(
            username: _username.text.trim(),
            password: _password.text,
            email: _email.text.trim(),
            phone: _phone.text.trim(),
            nickname: _nickname.text.trim(),
            code: _emailVerify ? _code.text.trim() : null,
          );
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
              const SnackBar(content: Text('注册成功，已自动登录')));
      }
    } catch (e) {
      if (mounted) _toast(apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  void dispose() {
    _username.dispose();
    _nickname.dispose();
    _password.dispose();
    _confirm.dispose();
    _email.dispose();
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('注册账号')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _username,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: '用户名 *',
                    prefixIcon: Icon(Icons.person_outline_rounded),
                    helperText: '3-50 个字符，登录时使用',
                  ),
                  validator: (v) {
                    final s = v?.trim() ?? '';
                    if (s.isEmpty) return '请输入用户名';
                    if (s.length < 3) return '用户名至少 3 个字符';
                    if (s.length > 50) return '用户名不能超过 50 个字符';
                    if (!RegExp(r'^[\w\u4e00-\u9fa5.@_-]+$').hasMatch(s)) {
                      return '用户名仅支持中文、字母、数字和 . @ _ -';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _nickname,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: '昵称',
                    prefixIcon: Icon(Icons.badge_outlined),
                    helperText: '选填，展示用名称，默认同用户名',
                  ),
                  validator: (v) =>
                      (v != null && v.trim().length > 50) ? '昵称不能超过 50 个字符' : null,
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _password,
                  obscureText: _obscure,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: '密码 *',
                    prefixIcon: const Icon(Icons.lock_outline_rounded),
                    helperText: '至少 6 位字符',
                    suffixIcon: IconButton(
                      icon: Icon(
                        _obscure
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined,
                        size: 20,
                      ),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                  validator: (v) {
                    if (v == null || v.isEmpty) return '请输入密码';
                    if (v.length < 6) return '密码至少 6 位字符';
                    return null;
                  },
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _confirm,
                  obscureText: _obscure,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: '确认密码 *',
                    prefixIcon: Icon(Icons.lock_reset_outlined),
                  ),
                  validator: (v) {
                    if (v == null || v.isEmpty) return '请再次输入密码';
                    if (v != _password.text) return '两次输入的密码不一致';
                    return null;
                  },
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: _emailVerify ? '邮箱 *' : '邮箱',
                    prefixIcon: const Icon(Icons.mail_outline_rounded),
                  ),
                  validator: (v) {
                    final s = v?.trim() ?? '';
                    if (s.isEmpty) {
                      return _emailVerify ? '开启邮箱验证时邮箱必填' : null;
                    }
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
                  textInputAction: TextInputAction.next,
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
                if (_emailVerify) ...[
                  const SizedBox(height: 14),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: _code,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: '邮箱验证码 *',
                            prefixIcon: Icon(Icons.mark_email_read_outlined),
                          ),
                          validator: (v) => (v == null || v.trim().isEmpty)
                              ? '请输入验证码'
                              : null,
                        ),
                      ),
                      const SizedBox(width: 10),
                      SizedBox(
                        height: 46,
                        child: OutlinedButton(
                          onPressed:
                              (_sendingCode || _codeCountdown > 0) ? null : _sendCode,
                          child: Text(
                            _codeCountdown > 0 ? '$_codeCountdown s' : '发送验证码',
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 26),
                FilledButton(
                  onPressed: _loading ? null : _submit,
                  child: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('注 册'),
                ),
                const SizedBox(height: 10),
                Text(
                  '注册成功后将自动登录',
                  textAlign: TextAlign.center,
                  style:
                      TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
