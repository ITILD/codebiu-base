import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../modules/agent/api/agent_service.dart';
import '../modules/ai/api/ai_service.dart';
import '../modules/authorization/api/auth_service.dart';
import '../modules/authorization/session.dart';
import '../modules/rag/api/rag_service.dart';
import 'services/api_error.dart';
import 'services/auth_interceptor.dart';
import 'settings.dart';

/// 应用核心（组合根）：统一持有 Dio / 设置 / 会话 / 各业务 Service
/// 说明：只有本文件允许同时依赖多个业务模块的 api 层，用于装配服务。
class AppCore {
  AppCore._({
    required this.prefs,
    required this.settings,
    required this.session,
  });

  final SharedPreferences prefs;
  final AppSettings settings;
  final SessionStore session;

  late final Dio dio;
  late final AuthService auth;
  late final AiService ai;
  late final RagService rag;
  late final AgentService agent;

  static Future<AppCore> create() async {
    final prefs = await SharedPreferences.getInstance();
    final settings = AppSettings(prefs)..load();
    final core = AppCore._(
      prefs: prefs,
      settings: settings,
      session: SessionStore(prefs)..load(),
    );
    core._init();
    return core;
  }

  void _init() {
    dio = Dio(BaseOptions(
      baseUrl: settings.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      sendTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 60),
    ));
    dio.interceptors.add(AuthInterceptor(this));
    auth = AuthService(dio, session);
    ai = AiService(dio);
    rag = RagService(dio);
    agent = AgentService(dio);
  }

  /// 修改服务器地址（设置页）
  void updateBaseUrl(String url) {
    settings.setBaseUrl(url);
    dio.options.baseUrl = url;
  }

  /// 将异常转为可读提示
  String errText(Object e) => apiErrorMessage(e);
}
