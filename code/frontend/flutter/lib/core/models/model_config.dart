/// AI 模型配置（对应后端 /ai/model-configs 返回项）
class ModelConfig {
  ModelConfig({
    required this.id,
    required this.model,
    required this.modelType,
    required this.serverType,
    this.displayName,
    this.scope,
    this.isDefault = false,
    this.isActive = true,
    this.checkValid,
  });

  final String id;
  final String model;
  final String modelType;
  final String serverType;
  final String? displayName;
  final String? scope;
  final bool isDefault;
  final bool isActive;
  final bool? checkValid;

  factory ModelConfig.fromJson(Map<String, dynamic> json) => ModelConfig(
        id: json['id']?.toString() ?? '',
        model: json['model']?.toString() ?? '',
        modelType: json['model_type']?.toString() ?? 'chat',
        serverType: json['server_type']?.toString() ?? 'openai',
        displayName: _str(json['display_name']),
        scope: _str(json['scope']),
        isDefault: json['is_default'] as bool? ?? false,
        isActive: json['is_active'] as bool? ?? true,
        checkValid: json['check_valid'] as bool?,
      );

  static String? _str(dynamic v) {
    final s = v?.toString().trim();
    return (s == null || s.isEmpty || s == 'null') ? null : s;
  }

  /// 列表展示名
  String get label {
    final n = displayName?.trim();
    return (n == null || n.isEmpty) ? model : n;
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'model': model,
        'model_type': modelType,
        'server_type': serverType,
        'display_name': displayName,
        'scope': scope,
        'is_default': isDefault,
        'is_active': isActive,
        'check_valid': checkValid,
      };
}

/// 分页列表响应（items/total/page/size/pages）
class PagedResult<T> {
  PagedResult({required this.items, required this.total});

  final List<T> items;
  final int total;
}
