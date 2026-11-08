import 'package:dio/dio.dart';

import '../session.dart';
import '../types/auth.dart';
import '../types/user.dart';

/// 认证相关接口（前缀 /authorization）
class AuthService {
  AuthService(this._dio, this._session);

  final Dio _dio;
  final SessionStore _session;

  static const _prefix = '/authorization/auth';

  /// 登录（OAuth2 表单编码）
  Future<AuthResponse> login(String username, String password,
      {String? code}) async {
    final data = <String, String>{
      'username': username,
      'password': password,
      if (code != null && code.isNotEmpty) 'code': code,
    };
    final resp = await _dio.post(
      '$_prefix/login',
      data: data,
      options:
          Options(contentType: Headers.formUrlEncodedContentType),
    );
    final auth = AuthResponse.fromJson(_asMap(resp.data));
    _session.saveAuth(auth);
    return auth;
  }

  /// 注册（成功即登录）
  Future<AuthResponse> register({
    required String username,
    required String password,
    String? email,
    String? phone,
    String? nickname,
    String? code,
    String? phoneCode,
  }) async {
    final resp = await _dio.post('$_prefix/register', data: {
      'username': username,
      'password': password,
      if (email != null && email.isNotEmpty) 'email': email,
      if (phone != null && phone.isNotEmpty) 'phone': phone,
      if (nickname != null && nickname.isNotEmpty) 'nickname': nickname,
      if (code != null && code.isNotEmpty) 'code': code,
      if (phoneCode != null && phoneCode.isNotEmpty) 'phone_code': phoneCode,
    });
    final auth = AuthResponse.fromJson(_asMap(resp.data));
    _session.saveAuth(auth);
    return auth;
  }

  /// 刷新 access 令牌（refresh 不轮换）
  Future<bool> refreshToken() async {
    final refresh = _session.refreshToken;
    if (refresh == null || refresh.isEmpty) return false;
    final resp = await _dio.post('$_prefix/refresh', data: {
      'token_refresh': refresh,
    });
    final data = _asMap(resp.data);
    final token = data['token']?.toString();
    if (token == null || token.isEmpty) return false;
    _session.saveAccess(TokenInfo.fromJson(data));
    return true;
  }

  /// 登出（吊销令牌并清空本地会话）
  Future<void> logout() async {
    final access = _session.accessToken ?? '';
    final refresh = _session.refreshToken ?? '';
    final refreshId = _session.refreshId ?? '';
    try {
      if (access.isNotEmpty) {
        await _dio.post('$_prefix/logout', data: {
          'token_access': access,
          'token_refresh': refresh,
          'token_refresh_id': refreshId,
        });
      }
    } finally {
      _session.clear();
    }
  }

  /// 当前用户信息
  Future<User> me() async {
    final resp = await _dio.get('$_prefix/me');
    final user = User.fromJson(_asMap(resp.data));
    _session.updateUser(user);
    return user;
  }

  /// 自助修改资料
  Future<User> updateProfile({
    String? nickname,
    String? email,
    String? phone,
    String? avatar,
  }) async {
    final resp = await _dio.put('$_prefix/me', data: {
      'nickname': ?nickname,
      'email': ?email,
      'phone': ?phone,
      'avatar': ?avatar,
    });
    final user = User.fromJson(_asMap(resp.data));
    _session.updateUser(user);
    return user;
  }

  /// 修改密码（需旧密码）
  Future<void> changePassword(String oldPassword, String newPassword) async {
    await _dio.put('$_prefix/me/password', data: {
      'old_password': oldPassword,
      'new_password': newPassword,
    });
  }

  /// 注册流程配置：是否需要邮箱/短信验证码
  Future<RegisterConfig> registerConfig() async {
    final resp = await _dio.get('$_prefix/register-config');
    return RegisterConfig.fromJson(_asMap(resp.data));
  }

  /// 登录策略：是否开启二次验证码
  Future<bool> loginMfaEnabled() async {
    final resp = await _dio.get('$_prefix/login-policy');
    return _asMap(resp.data)['mfa_enabled'] as bool? ?? false;
  }

  /// 发送注册验证码（邮箱或手机号）
  Future<void> sendRegisterCode({String? email, String? phone}) async {
    await _dio.post('$_prefix/register/code', data: {
      if (email != null && email.isNotEmpty) 'email': email,
      if (phone != null && phone.isNotEmpty) 'phone': phone,
    });
  }

  /// 发送登录二次验证码（发送至该用户绑定邮箱）
  Future<void> sendLoginCode(String username) async {
    await _dio.post('$_prefix/login/code', data: {'username': username});
  }

  static Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return data.cast<String, dynamic>();
    return <String, dynamic>{};
  }
}
