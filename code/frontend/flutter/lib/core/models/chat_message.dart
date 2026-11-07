/// 聊天消息
enum ChatRole { user, assistant }

class ChatMessage {
  ChatMessage({
    required this.role,
    required this.content,
    this.streaming = false,
    this.error,
    DateTime? time,
  }) : time = time ?? DateTime.now();

  final ChatRole role;
  String content;
  bool streaming;
  String? error;
  final DateTime time;

  bool get isError => error != null;

  /// 转为后端 /ai/llm/chat 的消息格式
  Map<String, dynamic> toApi() => {
        'role': role == ChatRole.user ? 'user' : 'assistant',
        'content': content,
      };

  /// 本地历史持久化（error/streaming 为瞬时状态，不落盘）
  Map<String, dynamic> toJson() => {
        'role': role == ChatRole.user ? 'user' : 'assistant',
        'content': content,
        'time': time.millisecondsSinceEpoch,
      };

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        role: json['role'] == 'user' ? ChatRole.user : ChatRole.assistant,
        content: json['content']?.toString() ?? '',
        time: DateTime.fromMillisecondsSinceEpoch(
            (json['time'] as num?)?.toInt() ?? 0),
      );
}
