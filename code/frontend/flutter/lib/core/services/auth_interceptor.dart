import 'package:dio/dio.dart';

import '../app_core.dart';

/// 认证拦截器：注入 Bearer Token；遇 401 自动刷新令牌并重放一次请求
class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor(this._core);

  final AppCore _core;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _core.session.accessToken;
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
      DioException err, ErrorInterceptorHandler handler) async {
    final status = err.response?.statusCode;
    final options = err.requestOptions;
    final path = options.path;
    final isAuthEndpoint = path.contains('/auth/login') ||
        path.contains('/auth/refresh') ||
        path.contains('/auth/register');

    if (status == 401 && !isAuthEndpoint && _core.session.canRefresh) {
      try {
        final ok = await _core.auth.refreshToken();
        if (ok) {
          final response = await _core.dio.fetch(options);
          return handler.resolve(response);
        }
      } catch (_) {
        // 刷新失败，走会话清理
      }
      _core.session.clear();
    }
    handler.next(err);
  }
}