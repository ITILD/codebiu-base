import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../core/app_core.dart';
import '../core/models/chat_message.dart';
import '../core/models/conversation.dart';
import '../core/models/model_config.dart';
import '../core/settings.dart';
import '../core/services/local_assistant.dart';

/// AI 对话状态：多会话历史 + 在线（SSE 流式）/ 本地（离线助手）
///
/// 会话历史持久化在本地（SharedPreferences，上限 50 条 / 每条 200 消息）；
/// 在线对话本身无服务端状态（/ai/llm/chat 无状态接口）。
class ChatProvider extends ChangeNotifier {
  ChatProvider(this._core) {
    _loadHistory();
  }

  final AppCore _core;

  static const _kHistory = 'chat.history.v1';
  static const _maxConversations = 50;
  static const _maxMessagesPerConversation = 200;

  final List<Conversation> conversations = <Conversation>[];
  late Conversation _active = _freshConversation();
  bool sending = false;

  List<ModelConfig> models = <ModelConfig>[];
  bool modelsLoading = false;
  String? modelsError;

  Conversation get active => _active;
  List<ChatMessage> get messages => _active.messages;
  bool get hasHistory => conversations.isNotEmpty;
  bool get isNewConversation => _active.messages.isEmpty;

  /// 当前生效的模型（在线模式）
  ModelConfig? get currentModel {
    final id = _core.settings.modelId;
    for (final m in models) {
      if (m.id == id) return m;
    }
    return null;
  }

  bool get isLocal => _core.settings.aiMode == AiMode.local;

  // ---------------- 会话管理 ----------------

  Conversation _freshConversation() => Conversation(
        id: DateTime.now().microsecondsSinceEpoch.toString(),
        title: '新对话',
        messages: <ChatMessage>[],
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
      );

  /// 新建对话（当前对话为空时无操作）
  void newConversation() {
    if (_active.messages.isEmpty) return;
    _active = _freshConversation();
    notifyListeners();
  }

  /// 切换到历史会话
  void switchTo(String id) {
    for (final c in conversations) {
      if (c.id == id && c != _active) {
        _active = c;
        notifyListeners();
        return;
      }
    }
  }

  /// 删除历史会话（若为当前会话则开启新对话）
  void removeConversation(String id) {
    conversations.removeWhere((c) => c.id == id);
    if (_active.id == id) {
      _active = _freshConversation();
    }
    _saveHistory();
    notifyListeners();
  }

  /// 清空当前对话（设置页入口）：等价删除当前会话并新建
  void clearConversation() {
    if (_active.messages.isEmpty) return;
    removeConversation(_active.id);
  }

  void _loadHistory() {
    try {
      final raw = _core.prefs.getString(_kHistory);
      if (raw == null || raw.isEmpty) return;
      final list = jsonDecode(raw);
      if (list is! List) return;
      conversations.clear();
      for (final item in list) {
        if (item is Map) {
          conversations
              .add(Conversation.fromJson(item.cast<String, dynamic>()));
        }
      }
      // 按更新时间倒序
      conversations.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    } catch (_) {
      // 历史损坏则忽略
    }
  }

  void _saveHistory() {
    try {
      final trimmed = conversations.take(_maxConversations).map((c) {
        if (c.messages.length > _maxMessagesPerConversation) {
          c.messages = c.messages.sublist(
              c.messages.length - _maxMessagesPerConversation);
        }
        return c;
      }).toList();
      _core.prefs.setString(
          _kHistory, jsonEncode(trimmed.map((c) => c.toJson()).toList()));
    } catch (_) {
      // 存储失败不影响会话
    }
  }

  // ---------------- 模型 ----------------

  /// 拉取模型配置列表（后端 /ai/model-configs），并确保已选中可用模型
  Future<void> loadModels({bool autoSelect = true}) async {
    modelsLoading = true;
    modelsError = null;
    notifyListeners();
    try {
      models = await _core.ai.chatModels();
      if (autoSelect) {
        _ensureSelection();
      }
    } catch (e) {
      modelsError = _core.errText(e);
    } finally {
      modelsLoading = false;
      notifyListeners();
    }
  }

  void _ensureSelection() {
    final active = models.where((m) => m.isActive).toList();
    if (active.isEmpty) return;
    final currentId = _core.settings.modelId;
    final exists = active.any((m) => m.id == currentId);
    if (!exists) {
      final preferred = active.firstWhere(
        (m) => m.isDefault,
        orElse: () => active.first,
      );
      _core.settings.setModelId(preferred.id);
    }
  }

  void selectModel(String id) {
    _core.settings.setModelId(id);
    notifyListeners();
  }

  void switchMode(AiMode mode) {
    _core.settings.setAiMode(mode);
    notifyListeners();
  }

  // ---------------- 发送 ----------------

  /// 发送一条用户消息并生成助手回复
  Future<void> send(String text) async {
    final content = text.trim();
    if (content.isEmpty || sending) return;
    messages.add(ChatMessage(role: ChatRole.user, content: content));
    final wasEmpty = _active.messages.length == 1;
    if (wasEmpty) {
      _active.title = Conversation.titleOf(content);
      conversations.insert(0, _active);
    }
    _active.updatedAt = DateTime.now();
    _saveHistory();

    final assistant = ChatMessage(
      role: ChatRole.assistant,
      content: '',
      streaming: true,
    );
    messages.add(assistant);
    sending = true;
    notifyListeners();

    try {
      if (isLocal) {
        await _replyLocal(assistant, content);
      } else {
        await _replyOnline(assistant);
      }
      assistant.streaming = false;
    } catch (e) {
      assistant.streaming = false;
      assistant.error = _core.errText(e);
    } finally {
      sending = false;
      _active.updatedAt = DateTime.now();
      _saveHistory();
      notifyListeners();
    }
  }

  /// 重试：移除末尾的失败回复并重发上一条用户消息
  Future<void> retryLast() async {
    if (sending || messages.isEmpty) return;
    while (messages.isNotEmpty &&
        messages.last.role == ChatRole.assistant &&
        (messages.last.isError || messages.last.content.isEmpty)) {
      messages.removeLast();
    }
    if (messages.isEmpty || messages.last.role != ChatRole.user) return;
    final lastUser = messages.removeLast();
    await send(lastUser.content);
  }

  Future<void> _replyOnline(ChatMessage assistant) async {
    final model = currentModel;
    if (model == null) {
      throw Exception('未选择在线模型，请先在菜单中选择模型');
    }
    // 组装上下文：排除错误消息与空占位（含当前流式占位气泡）
    final history = messages
        .where((m) => !m.isError && m.content.isNotEmpty)
        .map((m) => m.toApi())
        .toList();
    try {
      await for (final piece
          in _core.ai.streamChat(modelId: model.id, messages: history)) {
        assistant.content += piece;
        notifyListeners();
      }
    } catch (e) {
      if (assistant.content.isNotEmpty) {
        rethrow; // 已有部分内容，仅提示错误
      }
      // 首次流式失败：回退到非流式请求重试一次
      try {
        assistant.content =
            await _core.ai.chat(modelId: model.id, messages: history);
        notifyListeners();
        return;
      } catch (_) {
        rethrow;
      }
    }
    if (assistant.content.isEmpty) {
      throw Exception('模型未返回内容');
    }
  }

  Future<void> _replyLocal(ChatMessage assistant, String input) async {
    final full = LocalAssistant.reply(input);
    // 打字机效果：文本较长时加大步长，控制总时长约 1~2 秒
    final step = full.length > 80 ? (full.length / 60).ceil().clamp(2, 6) : 1;
    for (var i = 0; i < full.length; i += step) {
      assistant.content = full.substring(0, math.min(i + step, full.length));
      notifyListeners();
      await Future<void>.delayed(const Duration(milliseconds: 24));
    }
    assistant.content = full;
    notifyListeners();
  }
}
