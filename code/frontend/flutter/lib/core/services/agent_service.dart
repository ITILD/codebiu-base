import 'package:dio/dio.dart';

/// 智能体（Agent）模型与技能
class AgentInfo {
  AgentInfo({
    required this.id,
    required this.name,
    this.description,
    this.defaultPrompt,
    this.defaultProjectIds = const [],
    this.skills = const [],
    this.isPublic = false,
    this.isBuiltin = false,
    this.ownerUserId,
  });

  final String id;
  final String name;
  String? description;
  String? defaultPrompt;
  List<String> defaultProjectIds;
  List<String> skills;
  bool isPublic;
  final bool isBuiltin;
  final String? ownerUserId;

  factory AgentInfo.fromJson(Map<String, dynamic> json) => AgentInfo(
        id: json['id']?.toString() ?? '',
        name: json['name']?.toString() ?? '',
        description: _str(json['description']),
        defaultPrompt: _str(json['default_prompt']),
        defaultProjectIds:
            (json['default_project_ids'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        skills: (json['skills'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        isPublic: json['is_public'] as bool? ?? false,
        isBuiltin: json['is_builtin'] as bool? ?? false,
        ownerUserId: _str(json['owner_user_id']),
      );

  static String? _str(dynamic v) {
    final s = v?.toString().trim();
    return (s == null || s.isEmpty || s == 'null') ? null : s;
  }

  Map<String, dynamic> toCreate() => {
        'name': name,
        'description': description,
        'default_prompt': defaultPrompt,
        'default_project_ids': defaultProjectIds,
        'skills': skills,
        'is_public': isPublic,
      };
}

/// Agent 技能注册表项
class AgentSkill {
  AgentSkill(this.name, this.displayName, this.description);

  final String name;
  final String displayName;
  final String description;

  factory AgentSkill.fromJson(Map<String, dynamic> json) => AgentSkill(
        json['name']?.toString() ?? '',
        json['display_name']?.toString() ?? '',
        json['description']?.toString() ?? '',
      );
}

/// 智能体服务（前缀 /agent，全部需 Bearer；自建助手登录即可读写）
class AgentService {
  AgentService(this._dio);

  final Dio _dio;

  /// 可用技能注册表
  Future<List<AgentSkill>> skills() async {
    final resp = await _dio.get('/agent/skills');
    final data = resp.data;
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((e) => AgentSkill.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  /// 智能体列表（公开 + 本人）
  Future<List<AgentInfo>> agents() async {
    final resp = await _dio.get('/agent/agents');
    final data = resp.data;
    if (data is! List) return const [];
    return data
        .whereType<Map>()
        .map((e) => AgentInfo.fromJson(e.cast<String, dynamic>()))
        .toList();
  }

  Future<void> create(AgentInfo agent) async {
    await _dio.post('/agent/agents', data: agent.toCreate());
  }

  Future<void> update(String id, AgentInfo agent) async {
    await _dio.put('/agent/agents/$id', data: agent.toCreate());
  }

  Future<void> delete(String id) async {
    await _dio.delete('/agent/agents/$id');
  }
}
