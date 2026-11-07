import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'models/auth.dart';
import 'models/user.dart';

/// 登录会话存储：access/refresh 令牌 + 当前用户
class SessionStore {
  SessionStore(this._prefs);

  final SharedPreferences _prefs;

  static const _kAccess = 'session.access';
  static const _kRefresh = 'session.refresh';
  static const _kRefreshId = 'session.refresh_id';
  static const _kUser = 'session.user';

  String? accessToken;
  String? refreshToken;
  String? refreshId;
  User? user;

  void load() {
    accessToken = _prefs.getString(_kAccess);
    refreshToken = _prefs.getString(_kRefresh);
    refreshId = _prefs.getString(_kRefreshId);
    final raw = _prefs.getString(_kUser);
    if (raw != null && raw.isNotEmpty) {
      try {
        user = User.fromJson(
            jsonDecode(raw) as Map<String, dynamic>);
      } catch (_) {
        user = null;
      }
    }
  }

  bool get isLoggedIn => accessToken != null && accessToken!.isNotEmpty;
  bool get canRefresh => refreshToken != null && refreshToken!.isNotEmpty;

  /// 保存登录/注册返回的完整会话
  void saveAuth(AuthResponse resp) {
    accessToken = resp.access.token;
    refreshToken = resp.refresh.token;
    refreshId = resp.refresh.tokenId;
    user = resp.user;
    _persist();
  }

  /// 刷新后仅更新 access 令牌（refresh 不轮换）
  void saveAccess(TokenInfo access) {
    accessToken = access.token;
    _prefs.setString(_kAccess, access.token);
  }

  void updateUser(User u) {
    user = u;
    _persist();
  }

  void clear() {
    accessToken = null;
    refreshToken = null;
    refreshId = null;
    user = null;
    _prefs.remove(_kAccess);
    _prefs.remove(_kRefresh);
    _prefs.remove(_kRefreshId);
    _prefs.remove(_kUser);
  }

  void _persist() {
    _prefs.setString(_kAccess, accessToken ?? '');
    _prefs.setString(_kRefresh, refreshToken ?? '');
    _prefs.setString(_kRefreshId, refreshId ?? '');
    if (user != null) {
      _prefs.setString(
          _kUser, jsonEncode(user!.toJson()));
    }
  }
}
