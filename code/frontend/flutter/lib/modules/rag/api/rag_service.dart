import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';

import '../types/kb_project.dart';

/// RAG 知识库服务：项目与文档管理（前缀 /rag，全部需 Bearer）
class RagService {
  RagService(this._dio);

  final Dio _dio;

  /// 知识库项目列表
  Future<List<KbProject>> projects({String? name, int page = 1, int size = 100}) async {
    final resp = await _dio.get('/rag/projects/list', queryParameters: {
      'page': page,
      'size': size,
      if (name != null && name.isNotEmpty) 'name': name,
    });
    final items = resp.data is Map ? resp.data['items'] : null;
    if (items is! List) return const [];
    return items
        .whereType<Map>()
        .map((e) => KbProject.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  /// 创建项目 → 返回项目 ID
  Future<String> createProject({
    required String name,
    String? description,
    String kbCategory = 'project',
    bool isPrivate = true,
  }) async {
    final resp = await _dio.post('/rag/projects', data: {
      'name': name,
      'description': description,
      'kb_category': kbCategory,
      'is_private': isPrivate,
    });
    return resp.data?.toString() ?? '';
  }

  /// 更新项目（名称/描述等）
  Future<void> updateProject(String id, Map<String, dynamic> data) async {
    await _dio.put('/rag/projects/$id', data: data);
  }

  /// 删除项目
  Future<void> deleteProject(String id) async {
    await _dio.delete('/rag/projects/$id');
  }

  /// 项目文档列表
  Future<List<KbDocument>> documents(String projectId,
      {int page = 1, int size = 200}) async {
    final resp = await _dio.get(
      '/rag/project-documents/$projectId/list',
      queryParameters: {'page': page, 'size': size},
    );
    final items = resp.data is Map ? resp.data['items'] : null;
    if (items is! List) return const [];
    return items
        .whereType<Map>()
        .map((e) => KbDocument.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  /// 上传文档(预签名直传优先: init → 逐片直传/中转 → complete;
  /// 内容已存在时走秒传登记; proxy 模式小文件仍走服务端单次中转)
  Future<void> uploadDocument(
    String projectId,
    String filePath, {
    String? description,
  }) async {
    final fileName = filePath.split(Platform.pathSeparator).last;
    final file = File(filePath);
    final size = await file.length();
    final mode = await _uploadMode();

    // proxy(本地磁盘)小文件: 服务端单次中转, 免分片与哈希开销
    if (mode.mode == 'proxy' && size <= mode.maxSizeMb * 1024 * 1024) {
      final form = FormData.fromMap({
        'file': await MultipartFile.fromFile(filePath, filename: fileName),
        if (description != null && description.isNotEmpty)
          'description': description,
      });
      await _dio.post('/rag/project-documents/$projectId/upload', data: form);
      return;
    }

    final bytes = await file.readAsBytes();
    final contentHash = sha256.convert(bytes).toString();
    final init = await _dio.post(
      '/rag/project-documents/$projectId/multipart/init',
      data: {
        'filename': fileName,
        'file_size_bytes': size,
        'content_hash': contentHash,
        'content_type': _guessContentType(fileName),
      },
    );
    final initData = (init.data as Map).cast<String, dynamic>();
    // 服务端确认的落库名(同名自动加序号)
    final resolvedName = (initData['filename'] as String?) ?? fileName;

    // 秒传: 内容已存在, 直接登记文档
    if (initData['is_existing'] == true) {
      await _dio.post(
        '/rag/project-documents/$projectId/upload-complete',
        data: {
          'name': resolvedName,
          'content_hash': contentHash,
          'file_size_bytes': size,
          'mime_type': _guessContentType(fileName),
          if (description != null && description.isNotEmpty)
            'description': description,
        },
      );
      return;
    }

    final uploadId = initData['upload_id'] as String;
    final partSize = initData['part_size'] as int;
    final total = (size + partSize - 1) ~/ partSize;
    final parts = <Map<String, dynamic>>[];

    if (initData['mode'] == 'direct') {
      // 直传: 逐片 PUT 预签名URL(独立 Dio, 不带业务鉴权头, 数据面不经服务端)
      final urls = (initData['part_urls'] as List).cast<String>();
      final directDio = Dio();
      for (var i = 0; i < total; i++) {
        final start = i * partSize;
        final end = (start + partSize < size) ? start + partSize : size;
        final chunk = bytes.sublist(start, end);
        final resp = await directDio.put(
          urls[i],
          data: chunk,
          options: Options(headers: {'Content-Type': 'application/octet-stream'}),
        );
        parts.add({
          'part_number': i + 1,
          'etag': (resp.headers.value('etag') ?? '').replaceAll('"', ''),
          'size': chunk.length,
        });
      }
    } else {
      // 中转: 分片经服务端上传
      for (var i = 0; i < total; i++) {
        final start = i * partSize;
        final end = (start + partSize < size) ? start + partSize : size;
        final chunk = bytes.sublist(start, end);
        final resp = await _dio.put(
          '/rag/project-documents/$projectId/multipart/${Uri.encodeComponent(uploadId)}/parts/${i + 1}',
          data: chunk,
          options: Options(headers: {'Content-Type': 'application/octet-stream'}),
        );
        final part = (resp.data as Map).cast<String, dynamic>();
        parts.add({
          'part_number': part['part_number'] ?? i + 1,
          'etag': part['etag'] ?? '',
          'size': part['size'] ?? chunk.length,
        });
      }
    }

    await _dio.post(
      '/rag/project-documents/$projectId/multipart/${Uri.encodeComponent(uploadId)}/complete',
      data: {
        'filename': resolvedName,
        'file_size_bytes': size,
        'parts': parts,
        if (description != null && description.isNotEmpty)
          'description': description,
      },
    );
  }

  /// 查询上传模式(每次上传前查询, 参数变更后即时生效)
  Future<_RagUploadMode> _uploadMode() async {
    final resp = await _dio.get('/rag/project-documents/upload-mode');
    final data = (resp.data as Map).cast<String, dynamic>();
    return _RagUploadMode(
      mode: data['mode'] as String? ?? 'proxy',
      maxSizeMb: (data['max_size'] as num?)?.toDouble() ?? 10,
    );
  }

  /// 按扩展名推断 MIME(直传时无服务端 Content-Type 头)
  static String _guessContentType(String fileName) {
    final ext = fileName.split('.').last.toLowerCase();
    const mapping = {
      'pdf': 'application/pdf',
      'doc': 'application/msword',
      'docx':
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'xls': 'application/vnd.ms-excel',
      'xlsx':
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'ppt': 'application/vnd.ms-powerpoint',
      'pptx':
          'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'txt': 'text/plain',
      'md': 'text/markdown',
      'png': 'image/png',
      'jpg': 'image/jpeg',
      'jpeg': 'image/jpeg',
      'gif': 'image/gif',
      'webp': 'image/webp',
      'csv': 'text/csv',
    };
    return mapping[ext] ?? 'application/octet-stream';
  }

  /// 删除文档
  Future<void> deleteDocument(String documentId) async {
    await _dio.delete('/rag/project-documents/$documentId');
  }

  /// 重新解析文档
  Future<void> reparseDocument(String documentId) async {
    await _dio.post('/rag/project-documents/$documentId/reparse-task');
  }
}

/// 上传模式(direct=预签名直传 / proxy=服务端中转)
class _RagUploadMode {
  const _RagUploadMode({required this.mode, required this.maxSizeMb});

  final String mode;

  /// proxy 模式小文件直传上限(MB)
  final double maxSizeMb;
}
