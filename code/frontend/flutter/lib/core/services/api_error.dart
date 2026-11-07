import 'package:dio/dio.dart';

/// 统一把异常转换为面向用户的中文提示
String apiErrorMessage(Object e) {
  if (e is DioException) {
    final data = e.response?.data;
    if (data is Map && data['detail'] != null) {
      return data['detail'].toString();
    }
    switch (e.type) {
      case DioExceptionType.connectionError:
        return '无法连接服务器，请检查网络或服务器地址';
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return '连接服务器超时，请稍后重试';
      case DioExceptionType.badCertificate:
        return '服务器证书校验失败';
      case DioExceptionType.cancel:
        return '请求已取消';
      case DioExceptionType.badResponse:
        final code = e.response?.statusCode;
        return '请求失败（HTTP $code）';
      default:
        return e.message ?? '请求失败';
    }
  }
  return e.toString();
}

/// SSE 流中由后端报告的业务错误
class AiChatException implements Exception {
  AiChatException(this.message);

  final String message;

  @override
  String toString() => message;
}
