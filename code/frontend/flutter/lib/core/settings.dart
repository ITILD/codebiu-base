import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'constants.dart';

/// AI 助手运行模式
enum AiMode {
  /// 在线：调用后端 /ai 接口（服务器侧模型）
  online,

  /// 本地：客户端内置离线助手
  local;

  String get label => this == AiMode.online ? '在线' : '本地';

  static AiMode fromName(String? v) => v == 'local' ? AiMode.local : AiMode.online;
}

/// 应用设置（持久化到 SharedPreferences）
class AppSettings extends ChangeNotifier {
  AppSettings(this._prefs);

  final SharedPreferences _prefs;

  static const _kBaseUrl = 'settings.base_url';
  static const _kAiMode = 'settings.ai_mode';
  static const _kModelId = 'settings.model_id';
  static const _kThemeMode = 'settings.theme_mode';

  String baseUrl = AppConstants.defaultBaseUrl;
  AiMode aiMode = AiMode.online;
  String? modelId;
  ThemeMode themeMode = ThemeMode.system;

  void load() {
    baseUrl = _prefs.getString(_kBaseUrl) ?? AppConstants.defaultBaseUrl;
    aiMode = AiMode.fromName(_prefs.getString(_kAiMode));
    modelId = _prefs.getString(_kModelId);
    themeMode = ThemeMode.values.firstWhere(
      (e) => e.name == _prefs.getString(_kThemeMode),
      orElse: () => ThemeMode.system,
    );
  }

  void setBaseUrl(String url) {
    baseUrl = url;
    _prefs.setString(_kBaseUrl, url);
    notifyListeners();
  }

  void setAiMode(AiMode mode) {
    aiMode = mode;
    _prefs.setString(_kAiMode, mode.name);
    notifyListeners();
  }

  void setModelId(String? id) {
    modelId = id;
    if (id == null) {
      _prefs.remove(_kModelId);
    } else {
      _prefs.setString(_kModelId, id);
    }
    notifyListeners();
  }

  void setThemeMode(ThemeMode mode) {
    themeMode = mode;
    _prefs.setString(_kThemeMode, mode.name);
    notifyListeners();
  }
}
