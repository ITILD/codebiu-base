import 'user.dart';

/// 单个令牌信息（access / refresh 共用结构）
class TokenInfo {
  TokenInfo({required this.token, this.expiresIn = 0, this.tokenId});

  final String token;
  final int expiresIn;
  final String? tokenId;

  factory TokenInfo.fromJson(Map<String, dynamic> json) => TokenInfo(
        token: json['token']?.toString() ?? '',
        expiresIn: (json['expires_in'] as num?)?.toInt() ?? 0,
        tokenId: _str(json['token_id']),
      );

  static String? _str(dynamic v) {
    final s = v?.toString();
    return (s == null || s.isEmpty || s == 'null') ? null : s;
  }
}

/// 登录 / 注册成功响应（AuthResponse）
class AuthResponse {
  AuthResponse({
    required this.access,
    required this.refresh,
    required this.user,
    this.message = '',
  });

  final TokenInfo access;
  final TokenInfo refresh;
  final User user;
  final String message;

  factory AuthResponse.fromJson(Map<String, dynamic> json) {
    final tokens = (json['tokens'] as Map<String, dynamic>?) ?? {};
    return AuthResponse(
      access: TokenInfo.fromJson(
          (tokens['access'] as Map<String, dynamic>?) ?? {}),
      refresh: TokenInfo.fromJson(
          (tokens['refresh'] as Map<String, dynamic>?) ?? {}),
      user: User.fromJson((json['user'] as Map<String, dynamic>?) ?? {}),
      message: json['message']?.toString() ?? '',
    );
  }
}
