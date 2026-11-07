/// 用户模型（对应后端 UserResponse / User）
class User {
  User({
    required this.id,
    required this.username,
    this.deptId,
    this.email,
    this.phone,
    this.nickname,
    this.avatar,
    this.isActive = true,
    this.createdAt,
    this.updatedAt,
  });

  final String id;
  final String username;
  final String? deptId;
  final String? email;
  final String? phone;
  final String? nickname;
  final String? avatar;
  final bool isActive;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id']?.toString() ?? '',
        username: json['username']?.toString() ?? '',
        deptId: _str(json['dept_id']),
        email: _str(json['email']),
        phone: _str(json['phone']),
        nickname: _str(json['nickname']),
        avatar: _str(json['avatar']),
        isActive: json['is_active'] as bool? ?? true,
        createdAt: _date(json['created_at']),
        updatedAt: _date(json['updated_at']),
      );

  static String? _str(dynamic v) {
    final s = v?.toString().trim();
    return (s == null || s.isEmpty || s == 'null') ? null : s;
  }

  static DateTime? _date(dynamic v) =>
      v == null ? null : DateTime.tryParse(v.toString());

  /// 展示名：昵称优先，缺省用用户名
  String get displayName {
    final n = nickname?.trim();
    return (n == null || n.isEmpty) ? username : n;
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'dept_id': deptId,
        'email': email,
        'phone': phone,
        'nickname': nickname,
        'avatar': avatar,
        'is_active': isActive,
        'created_at': createdAt?.toIso8601String(),
        'updated_at': updatedAt?.toIso8601String(),
      };

  User copyWith({
    String? deptId,
    String? email,
    String? phone,
    String? nickname,
    String? avatar,
  }) =>
      User(
        id: id,
        username: username,
        deptId: deptId ?? this.deptId,
        email: email ?? this.email,
        phone: phone ?? this.phone,
        nickname: nickname ?? this.nickname,
        avatar: avatar ?? this.avatar,
        isActive: isActive,
        createdAt: createdAt,
        updatedAt: DateTime.now(),
      );
}
