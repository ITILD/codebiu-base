import 'package:flutter/foundation.dart';

import '../core/app_core.dart';
import '../core/models/user.dart';

/// 认证状态：启动引导 / 登录 / 注册 / 登出 / 用户资料
class AuthProvider extends ChangeNotifier {
  AuthProvider(this._core);

  final AppCore _core;

  User? user;
  bool booting = true;

  AppCore get core => _core;

  /// 启动：恢复本地会话并校验
  Future<void> bootstrap() async {
    final session = _core.session;
    if (session.isLoggedIn) {
      try {
        user = await _core.auth.me();
      } catch (_) {
        // 校验失败（令牌过期且无法刷新）时清理会话，回到登录页
        if (!session.isLoggedIn) {
          user = null;
        } else {
          user = session.user;
        }
      }
    } else {
      user = null;
    }
    booting = false;
    notifyListeners();
  }

  Future<void> login(String username, String password, {String? code}) async {
    final resp = await _core.auth.login(username, password, code: code);
    user = resp.user;
    notifyListeners();
  }

  Future<void> register({
    required String username,
    required String password,
    String? email,
    String? phone,
    String? nickname,
    String? code,
  }) async {
    final resp = await _core.auth.register(
      username: username,
      password: password,
      email: email,
      phone: phone,
      nickname: nickname,
      code: code,
    );
    user = resp.user;
    notifyListeners();
  }

  Future<void> updateProfile({
    String? nickname,
    String? email,
    String? phone,
    String? avatar,
  }) async {
    user = await _core.auth.updateProfile(
      nickname: nickname,
      email: email,
      phone: phone,
      avatar: avatar,
    );
    notifyListeners();
  }

  Future<void> logout() async {
    try {
      await _core.auth.logout();
    } finally {
      user = null;
      notifyListeners();
    }
  }

  /// 供拦截器在令牌彻底失效时强制回到登录页
  void forceSignedOut() {
    user = null;
    notifyListeners();
  }
}
