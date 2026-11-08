import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../common/services/api_error.dart';
import '../providers/auth_provider.dart';

/// 注册页（邮箱/短信验证码按后端注册配置自适应）
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
  final _emailCode = TextEditingController();
  final _smsCode = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  bool _sendingEmailCode = false;
  bool _sendingSmsCode = false;
  bool _emailVerify = false;
  bool _smsVerify = false;
  int _emailCountdown = 0;
  int _smsCountdown = 0;

  @override
  void initState() {
    super.initState();
    _loadConfig();
  }

  /// 拉取注册配置：是否需要邮箱/短信验证码
  Future<void> _loadConfig() async {
    try {
      final config =
          await context.read<AuthProvider>().core.auth.registerConfig();
      if (mounted) {
        setState(() {
          _emailVerify = config.emailVerify;
          _smsVerify = config.smsVerify;
        });
      }
    } catch (_) {
      // 拉取失败按无需验证码处理
    }
  }

  /// 发送验证码（isPhone=true 走短信，否则走邮箱）
  Future<void> _sendCode({required bool isPhone}) async {
    final target = (isPhone ? _phone : _email).text.trim();
    final valid = isPhone
        ? RegExp(r'^1\d{10}$').hasMatch(target)
        : RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(target);
    if (!valid) {
      _toast(isPhone ? '请先输入正确的手机号' : '请先输入正确的邮箱地址');
      return;
    }
    setState(() {
      if (isPhone) {
        _sendingSmsCode = true;
      } else {
        _sendingEmailCode = true;
      }
    });
    try {
      await context.read<AuthProvider>().core.auth.sendRegisterCode(
            email: isPhone ? null : target,
            phone: isPhone ? target : null,
          );
      if (!mounted) return;
      _toast(isPhone ? '验证码已发送，请查收短信' : '验证码已发送，请查收邮箱');
      setState(() {
        if (isPhone) {
          _smsCountdown = 60;
        } else {
          _emailCountdown = 60;
        }
      });
      _startCountdown(isPhone: isPhone);
    } catch (e) {
      if (mounted) _toast(apiErrorMessage(e));
    } finally {
      if (mounted) {
        setState(() {
          if (isPhone) {
            _sendingSmsCode = false;
          } else {
            _sendingEmailCode = false;
          }
        });
      }
    }
  }

  /// 验证码重发倒计时
  void _startCountdown({required bool isPhone}) {
    Future.doWhile(() async {
      await Future<void>.delayed(const Duration(seconds: 1));
      if (!mounted) return false;
      setState(() {
        if (isPhone) {
          _smsCountdown--;
        } else {
          _emailCountdown--;
        }
      });
      return (isPhone ? _smsCountdown : _emailCountdown) > 0;
    });
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
            code: _emailVerify ? _emailCode.text.trim() : null,
            phoneCode: _smsVerify ? _smsCode.text.trim() : null,
          );
      if (mounted) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(const SnackBar(content: Text('注册成功，已自动登录')));
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
    _emailCode.dispose();
    _smsCode.dispose();
    super.dispose();
  }

  /// 验证码输入行（输入框 + 发送按钮）
  Widget _codeRow({
    required TextEditingController controller,
    required bool isPhone,
    required int countdown,
    required bool sending,
    required IconData icon,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextFormField(
            controller: controller,
            keyboardType: TextInputType.number,
            decoration: InputDecoration(
              labelText: isPhone ? '短信验证码 *' : '邮箱验证码 *',
              prefixIcon: Icon(icon),
            ),
            validator: (v) =>
                (v == null || v.trim().isEmpty) ? '请输入验证码' : null,
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          height: 46,
          child: OutlinedButton(
            onPressed: (sending || countdown > 0)
                ? null
                : () => _sendCode(isPhone: isPhone),
            child: Text(
              countdown > 0 ? '$countdown s' : '发送验证码',
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ),
      ],
    );
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
                if (_emailVerify) ...[
                  const SizedBox(height: 14),
                  _codeRow(
                    controller: _emailCode,
                    isPhone: false,
                    countdown: _emailCountdown,
                    sending: _sendingEmailCode,
                    icon: Icons.mark_email_read_outlined,
                  ),
                ],
                const SizedBox(height: 14),
                TextFormField(
                  controller: _phone,
                  keyboardType: TextInputType.phone,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: _smsVerify ? '手机号 *' : '手机号',
                    prefixIcon: const Icon(Icons.phone_outlined),
                  ),
                  validator: (v) {
                    final s = v?.trim() ?? '';
                    if (s.isEmpty) {
                      return _smsVerify ? '开启短信验证时手机号必填' : null;
                    }
                    if (_smsVerify) {
                      return RegExp(r'^1\d{10}$').hasMatch(s) ? null : '请输入 11 位大陆手机号';
                    }
                    if (!RegExp(r'^\+?\d{5,20}$').hasMatch(s)) {
                      return '手机号格式不正确';
                    }
                    return null;
                  },
                ),
                if (_smsVerify) ...[
                  const SizedBox(height: 14),
                  _codeRow(
                    controller: _smsCode,
                    isPhone: true,
                    countdown: _smsCountdown,
                    sending: _sendingSmsCode,
                    icon: Icons.sms_outlined,
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
