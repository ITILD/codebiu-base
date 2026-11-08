import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../common/services/api_error.dart';
import '../providers/auth_provider.dart';
import 'register_page.dart';
import '../../main/pages/settings_page.dart';

/// 登录页
class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  bool _sendingCode = false;
  bool _mfaEnabled = false;
  int _codeCountdown = 0;

  @override
  void initState() {
    super.initState();
    _loadPolicy();
  }

  Future<void> _loadPolicy() async {
    try {
      final enabled =
          await context.read<AuthProvider>().core.auth.loginMfaEnabled();
      if (mounted) {
        setState(() => _mfaEnabled = enabled);
      }
    } catch (_) {
      // 拉取失败按未开启处理
    }
  }

  Future<void> _sendCode() async {
    final username = _username.text.trim();
    if (username.isEmpty) {
      _toast('请先输入用户名');
      return;
    }
    setState(() => _sendingCode = true);
    try {
      await context.read<AuthProvider>().core.auth.sendLoginCode(username);
      if (!mounted) return;
      _toast('验证码已发送至绑定邮箱');
      _startCountdown();
    } catch (e) {
      if (mounted) _toast(apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _sendingCode = false);
    }
  }

  void _startCountdown() {
    setState(() => _codeCountdown = 60);
    Future.doWhile(() async {
      await Future<void>.delayed(const Duration(seconds: 1));
      if (!mounted) return false;
      setState(() => _codeCountdown--);
      return _codeCountdown > 0;
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    try {
      await context.read<AuthProvider>().login(
            _username.text.trim(),
            _password.text,
            code: _mfaEnabled ? _code.text.trim() : null,
          );
      // 成功后 AuthGate 自动切换
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
    _password.dispose();
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('登录'),
        actions: [
          IconButton(
            tooltip: '设置',
            icon: const Icon(Icons.settings_outlined, size: 20),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const SettingsPage()),
            ),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 400),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 品牌区
                    Container(
                      width: 60,
                      height: 60,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: scheme.primary,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Icon(Icons.smart_toy_rounded,
                          color: scheme.onPrimary, size: 30),
                    ),
                    const SizedBox(height: 12),
                    Text('CodeBiu',
                        textAlign: TextAlign.center,
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text('欢迎使用 CodeBiu 客户端',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 13, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 28),

                    TextFormField(
                      controller: _username,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.username],
                      decoration: const InputDecoration(
                        labelText: '用户名',
                        prefixIcon: Icon(Icons.person_outline_rounded),
                      ),
                      validator: (v) =>
                          (v == null || v.trim().isEmpty) ? '请输入用户名' : null,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: _password,
                      obscureText: _obscure,
                      textInputAction: _mfaEnabled
                          ? TextInputAction.next
                          : TextInputAction.done,
                      onFieldSubmitted: (_) => _mfaEnabled ? null : _submit(),
                      autofillHints: const [AutofillHints.password],
                      decoration: InputDecoration(
                        labelText: '密码',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
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
                      validator: (v) =>
                          (v == null || v.isEmpty) ? '请输入密码' : null,
                    ),
                    if (_mfaEnabled) ...[
                      const SizedBox(height: 14),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: TextFormField(
                              controller: _code,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(
                                labelText: '邮箱验证码',
                                prefixIcon:
                                    Icon(Icons.mark_email_read_outlined),
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
                                  (_sendingCode || _codeCountdown > 0)
                                      ? null
                                      : _sendCode,
                              child: Text(
                                _codeCountdown > 0 ? '$_codeCountdown s' : '发送验证码',
                                style: const TextStyle(fontSize: 13),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: _loading ? null : _submit,
                      child: _loading
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('登 录'),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text('还没有账号？',
                            style: TextStyle(
                                fontSize: 13, color: scheme.onSurfaceVariant)),
                        TextButton(
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute<void>(
                                builder: (_) => const RegisterPage()),
                          ),
                          child: const Text('立即注册',
                              style: TextStyle(fontSize: 13)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
