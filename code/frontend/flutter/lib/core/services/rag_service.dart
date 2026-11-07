import 'dart:io';

import 'package:dio/dio.dart';

import '../models/kb_project.dart';

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

  /// 上传文档（multipart 字段 file；上传后自动派发解析任务）
  Future<void> uploadDocument(
    String projectId,
    String filePath, {
    String? description,
  }) async {
    final fileName = filePath.split(Platform.pathSeparator).last;
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(filePath, filename: fileName),
      if (description != null && description.isNotEmpty)
        'description': description,
    });
    await _dio.post('/rag/project-documents/$projectId/upload', data: form);
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
