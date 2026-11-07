import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/app_core.dart';
import '../core/models/kb_project.dart';
import '../core/services/api_error.dart';

/// 知识库状态：项目列表 + 当前项目的文档列表（含解析进度轮询）
class RagProvider extends ChangeNotifier {
  RagProvider(this._core);

  final AppCore _core;

  List<KbProject> projects = <KbProject>[];
  bool loading = false;
  String? error;

  String? currentProjectId;
  List<KbDocument> docs = <KbDocument>[];
  bool docsLoading = false;
  String? docsError;
  Timer? _pollTimer;
  bool _uploading = false;

  bool get uploading => _uploading;
  bool get hasParsing =>
      docs.any((d) => d.parseStatus == 'parsing' || d.parseStatus == 'pending');

  // ---------------- 项目 ----------------

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      projects = await _core.rag.projects();
    } catch (e) {
      error = apiErrorMessage(e);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<String?> createProject({
    required String name,
    String? description,
    String kbCategory = 'project',
    bool isPrivate = true,
  }) async {
    try {
      await _core.rag.createProject(
        name: name,
        description: description,
        kbCategory: kbCategory,
        isPrivate: isPrivate,
      );
      await load();
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  Future<String?> renameProject(KbProject p, String name, String? desc) async {
    try {
      await _core.rag
          .updateProject(p.id, {'name': name, 'description': desc});
      await load();
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  Future<String?> deleteProject(String id) async {
    try {
      await _core.rag.deleteProject(id);
      if (currentProjectId == id) {
        currentProjectId = null;
        docs = const [];
        _stopPolling();
      }
      await load();
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  // ---------------- 文档 ----------------

  Future<void> loadDocs(String projectId) async {
    currentProjectId = projectId;
    docsLoading = true;
    docsError = null;
    notifyListeners();
    try {
      docs = await _core.rag.documents(projectId);
    } catch (e) {
      docsError = apiErrorMessage(e);
    } finally {
      docsLoading = false;
      notifyListeners();
      _schedulePolling();
    }
  }

  Future<String?> uploadDoc(String projectId, String filePath) async {
    _uploading = true;
    notifyListeners();
    try {
      await _core.rag.uploadDocument(projectId, filePath);
      await loadDocs(projectId);
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    } finally {
      _uploading = false;
      notifyListeners();
    }
  }

  Future<String?> deleteDoc(String docId) async {
    try {
      await _core.rag.deleteDocument(docId);
      if (currentProjectId != null) {
        docs.removeWhere((d) => d.id == docId);
        notifyListeners();
      }
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  Future<String?> reparseDoc(String docId) async {
    try {
      await _core.rag.reparseDocument(docId);
      if (currentProjectId != null) {
        await loadDocs(currentProjectId!);
      }
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  /// 存在解析中的文档时每 3 秒刷新一次进度
  void _schedulePolling() {
    _stopPolling();
    if (!hasParsing || currentProjectId == null) return;
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      final pid = currentProjectId;
      if (pid == null) return _stopPolling();
      try {
        docs = await _core.rag.documents(pid);
      } catch (_) {
        return;
      }
      notifyListeners();
      if (!hasParsing) _stopPolling();
    });
  }

  void _stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  @override
  void dispose() {
    _stopPolling();
    super.dispose();
  }
}
