import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../models/model_config.dart';
import 'api_error.dart';

/// AI 能力接口（前缀 /ai）
class AiService {
  AiService(this._dio);

  final Dio _dio;

  /// 获取 chat 类模型配置列表（需登录）
  Future<List<ModelConfig>> chatModels() async {
    final resp = await _dio.get(
      '/ai/model-configs/list',
      queryParameters: {
        'model_type': 'chat',
        'page': 1,
        'size': 200,
      },
    );
    final data = resp.data;
    final items = data is Map ? data['items'] : null;
    if (items is! List) return const [];
    return items
        .whereType<Map>()
        .map((e) => ModelConfig.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  /// 流式对话（SSE legacy 协议），逐段返回正文内容
  Stream<String> streamChat({
    required String modelId,
    required List<Map<String, dynamic>> messages,
  }) async* {
    final response = await _dio.post<ResponseBody>(
      '/ai/llm/chat',
      data: {
        'model_id': modelId,
        'messages': messages,
        'streaming': true,
        'event_protocol': 'legacy',
      },
      options: Options(
        responseType: ResponseType.stream,
        headers: {Headers.acceptHeader: 'text/event-stream'},
        receiveTimeout: null,
      ),
    );
    final body = response.data;
    if (body == null) {
      throw AiChatException('服务器未返回内容');
    }

    var buffer = '';
    await for (final chunk in body.stream) {
      buffer += utf8.decode(chunk, allowMalformed: true);
      while (true) {
        final idx = buffer.indexOf('\n');
        if (idx < 0) break;
        final line = buffer.substring(0, idx).trimRight();
        buffer = buffer.substring(idx + 1);
        final piece = _parseSseLine(line);
        if (piece != null) yield piece;
      }
    }
    if (buffer.trim().isNotEmpty) {
      final piece = _parseSseLine(buffer.trim());
      if (piece != null) yield piece;
    }
  }

  /// 非流式对话（返回完整字符串）
  Future<String> chat({
    required String modelId,
    required List<Map<String, dynamic>> messages,
  }) async {
    final resp = await _dio.post(
      '/ai/llm/chat',
      data: {
        'model_id': modelId,
        'messages': messages,
        'streaming': false,
      },
      options: Options(responseType: ResponseType.plain),
    );
    final data = resp.data;
    if (data is String) return data;
    if (data is Map && data['detail'] != null) {
      throw AiChatException(data['detail'].toString());
    }
    return data.toString();
  }

  /// 解析单条 SSE data 行，返回正文增量；null 表示无需输出
  String? _parseSseLine(String line) {
    if (!line.startsWith('data:')) return null;
    final payload = line.substring(5).trim();
    if (payload.isEmpty || payload == '[DONE]') return null;
    dynamic json;
    try {
      json = jsonDecode(payload);
    } catch (_) {
      return payload; // 非标准 JSON，原样输出
    }
    if (json is! Map) return payload;
    final status = json['status']?.toString() ?? 'stream';
    if (status == 'error') {
      throw AiChatException(
          json['content']?.toString() ?? '模型返回错误');
    }
    if (status == 'stream' || status == 'start') {
      final content = json['content']?.toString();
      return (content == null || content.isEmpty) ? null : content;
    }
    return null;
  }
}
