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
    this.agentKind = 'chat',
    this.decisionMode = 'model',
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

  /// 形态：chat 会话 / job 批处理（REQ-018；本客户端只管理 chat，job 仅显示徽标）
  final String agentKind;

  /// 决策方式：rule 固定步骤 / model 模型决策 / hybrid 混合
  final String decisionMode;

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
        agentKind: json['agent_kind']?.toString() ?? 'chat',
        decisionMode: json['decision_mode']?.toString() ?? 'model',
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

/// Agent 技能注册表项（/agent/skills 返回的 Manifest 视图，REQ-018）
class AgentSkill {
  AgentSkill({
    required this.key,
    required this.name,
    this.description = '',
    this.nature = '',
    this.agentCallable = true,
  });

  /// 全局键（如 sys.web_search），技能多选的 value
  final String key;

  /// 展示名（如 网络搜索），技能多选的 label
  final String name;
  final String description;

  /// 实现性质：static=规则 / ai=模型 / hybrid=混合
  final String nature;

  /// 是否可被对话 tool-calling 调用；false 时选择器中禁用
  final bool agentCallable;

  factory AgentSkill.fromJson(Map<String, dynamic> json) {
    final key = json['key']?.toString() ?? '';
    return AgentSkill(
      key: key,
      name: json['name']?.toString() ?? key,
      description: json['description']?.toString() ?? '',
      nature: json['nature']?.toString() ?? '',
      agentCallable: json['agent_callable'] as bool? ?? true,
    );
  }
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
