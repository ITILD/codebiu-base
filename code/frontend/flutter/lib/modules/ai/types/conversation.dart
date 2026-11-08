import 'chat_message.dart';

/// 本地会话（历史记录），持久化到 SharedPreferences
class Conversation {
  Conversation({
    required this.id,
    required this.title,
    required this.messages,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  String title;
  List<ChatMessage> messages;
  final DateTime createdAt;
  DateTime updatedAt;

  /// 从首条用户消息提取标题
  static String titleOf(String text) {
    final t = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    return t.length > 18 ? '${t.substring(0, 18)}…' : t;
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'messages':
            messages.map((m) => m.toJson()).toList(growable: false),
        'created_at': createdAt.millisecondsSinceEpoch,
        'updated_at': updatedAt.millisecondsSinceEpoch,
      };

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
        id: json['id']?.toString() ?? '',
        title: json['title']?.toString() ?? '对话',
        messages: ((json['messages'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => ChatMessage.fromJson(m.cast<String, dynamic>()))
            .toList(),
        createdAt: DateTime.fromMillisecondsSinceEpoch(
            (json['created_at'] as num?)?.toInt() ?? 0),
        updatedAt: DateTime.fromMillisecondsSinceEpoch(
            (json['updated_at'] as num?)?.toInt() ?? 0),
      );
}
