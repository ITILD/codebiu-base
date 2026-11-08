/// 知识库项目（对应后端 ProjectResponse）
class KbProject {
  KbProject({
    required this.id,
    required this.name,
    this.description,
    required this.kbCategory,
    required this.isPrivate,
    this.createdBy,
    this.createdAt,
    this.canUpdate = false,
    this.canDelete = false,
  });

  final String id;
  final String name;
  final String? description;
  final String kbCategory; // personal / project / company
  final bool isPrivate;
  final String? createdBy;
  final DateTime? createdAt;
  final bool canUpdate;
  final bool canDelete;

  factory KbProject.fromJson(Map<String, dynamic> json) {
    final perms = json['my_perms'];
    return KbProject(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      description: _str(json['description']),
      kbCategory: json['kb_category']?.toString() ?? 'project',
      isPrivate: json['is_private'] as bool? ?? true,
      createdBy: _str(json['created_by']),
      createdAt: _date(json['created_at']),
      canUpdate: perms is Map && (perms['update'] as bool? ?? false),
      canDelete: perms is Map && (perms['delete'] as bool? ?? false),
    );
  }

  static String? _str(dynamic v) {
    final s = v?.toString().trim();
    return (s == null || s.isEmpty || s == 'null') ? null : s;
  }

  static DateTime? _date(dynamic v) =>
      v == null ? null : DateTime.tryParse(v.toString());

  String get categoryLabel =>
      { 'personal': '个人', 'project': '项目', 'company': '公司' }[kbCategory] ?? kbCategory;
}

/// 知识库文档（对应后端 ProjectDocumentResponse）
class KbDocument {
  KbDocument({
    required this.id,
    required this.projectId,
    required this.name,
    this.fileExtension,
    this.fileSizeBytes = 0,
    this.parseStatus = 'pending',
    this.chunkCount = 0,
    this.errorMessage,
    this.description,
    this.createdAt,
  });

  final String id;
  final String projectId;
  final String name;
  final String? fileExtension;
  final int fileSizeBytes;
  final String parseStatus; // pending / parsing / completed / failed
  final int chunkCount;
  final String? errorMessage;
  final String? description;
  final DateTime? createdAt;

  factory KbDocument.fromJson(Map<String, dynamic> json) => KbDocument(
        id: json['id']?.toString() ?? '',
        projectId: json['project_id']?.toString() ?? '',
        name: json['name']?.toString() ?? '',
        fileExtension: KbProject._str(json['file_extension']),
        fileSizeBytes: (json['file_size_bytes'] as num?)?.toInt() ?? 0,
        parseStatus: json['parse_status']?.toString() ?? 'pending',
        chunkCount: (json['chunk_count'] as num?)?.toInt() ?? 0,
        errorMessage: KbProject._str(json['error_message']),
        description: KbProject._str(json['description']),
        createdAt: KbProject._date(json['created_at']),
      );

  String get sizeLabel {
    if (fileSizeBytes <= 0) return '';
    if (fileSizeBytes < 1024) return '$fileSizeBytes B';
    if (fileSizeBytes < 1024 * 1024) {
      return '${(fileSizeBytes / 1024).toStringAsFixed(1)} KB';
    }
    return '${(fileSizeBytes / 1024 / 1024).toStringAsFixed(1)} MB';
  }
}
