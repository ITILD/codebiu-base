import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/models/kb_project.dart';
import '../../providers/rag_provider.dart';

/// 知识库文档管理：上传 / 解析状态 / 重新解析 / 删除
class KbProjectPage extends StatefulWidget {
  const KbProjectPage({super.key, required this.project});

  final KbProject project;

  @override
  State<KbProjectPage> createState() => _KbProjectPageState();
}

class _KbProjectPageState extends State<KbProjectPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        context.read<RagProvider>().loadDocs(widget.project.id);
      }
    });
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  static const _allowed = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'png', 'jpg', 'jpeg'];

  Future<void> _pickAndUpload() async {
    final rag = context.read<RagProvider>();
    final picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: _allowed,
    );
    if (picked.isEmpty) return;
    final path = picked.first.path;
    if (path == null) return;
    _toast('正在上传…');
    final err = await rag.uploadDoc(widget.project.id, path);
    if (!mounted) return;
    _toast(err ?? '已上传，正在解析');
  }

  Future<void> _confirmDelete(String docId, String name) async {
    final scheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除文档'),
        content: Text('将删除「$name」及其向量数据，不可恢复。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('取消')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: scheme.error,
                minimumSize: const Size(64, 36)),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (ok == true && mounted) {
      final err = await context.read<RagProvider>().deleteDoc(docId);
      if (mounted) _toast(err ?? '已删除');
    }
  }

  IconData _fileIcon(String? ext) {
    switch (ext?.toLowerCase()) {
      case 'pdf':
        return Icons.picture_as_pdf_outlined;
      case 'png':
      case 'jpg':
      case 'jpeg':
        return Icons.image_outlined;
      case 'doc':
      case 'docx':
        return Icons.description_outlined;
      case 'ppt':
      case 'pptx':
        return Icons.slideshow_outlined;
      default:
        return Icons.insert_drive_file_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final rag = context.watch<RagProvider>();
    final docs = rag.docs;

    Widget body;
    if (rag.docsLoading && docs.isEmpty) {
      body = const Center(
          child: CircularProgressIndicator(strokeWidth: 2.4));
    } else if (rag.docsError != null && docs.isEmpty) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded, size: 40, color: scheme.onSurfaceVariant),
            const SizedBox(height: 10),
            Text(rag.docsError!,
                style: TextStyle(
                    fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () =>
                  context.read<RagProvider>().loadDocs(widget.project.id),
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('重试', style: TextStyle(fontSize: 13)),
            ),
          ],
        ),
      );
    } else if (docs.isEmpty) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.upload_file_outlined,
                size: 42, color: scheme.onSurfaceVariant),
            const SizedBox(height: 12),
            const Text('还没有文档',
                style: TextStyle(fontSize: 13.5)),
            const SizedBox(height: 6),
            Text('支持 ${_allowed.join(' / ')}',
                style: TextStyle(
                    fontSize: 12, color: scheme.onSurfaceVariant)),
          ],
        ),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: () =>
            context.read<RagProvider>().loadDocs(widget.project.id),
        child: ListView.separated(
          padding: const EdgeInsets.all(12),
          itemCount: docs.length,
          separatorBuilder: (_, _) => const SizedBox(height: 6),
          itemBuilder: (_, i) {
            final d = docs[i];
            return Card(
              child: ListTile(
                leading: Icon(_fileIcon(d.fileExtension),
                    size: 22, color: scheme.primary),
                title: Text(d.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w500)),
                subtitle: Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Row(
                    children: [
                      _statusChip(scheme, d),
                      const SizedBox(width: 6),
                      if (d.sizeLabel.isNotEmpty)
                        Text(d.sizeLabel,
                            style: TextStyle(
                                fontSize: 11,
                                color: scheme.onSurfaceVariant)),
                      if (d.parseStatus == 'completed' && d.chunkCount > 0) ...[
                        const SizedBox(width: 6),
                        Text('${d.chunkCount} 块',
                            style: TextStyle(
                                fontSize: 11,
                                color: scheme.onSurfaceVariant)),
                      ],
                    ],
                  ),
                ),
                trailing: PopupMenuButton<String>(
                  icon: Icon(Icons.more_vert_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onSelected: (a) async {
                    if (a == 'reparse') {
                      final err = await context
                          .read<RagProvider>()
                          .reparseDoc(d.id);
                      if (mounted) _toast(err ?? '已触发重新解析');
                    } else if (a == 'delete') {
                      _confirmDelete(d.id, d.name);
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                        value: 'reparse',
                        height: 42,
                        child: Row(children: [
                          Icon(Icons.refresh_rounded, size: 17),
                          SizedBox(width: 8),
                          Text('重新解析', style: TextStyle(fontSize: 13)),
                        ])),
                    PopupMenuItem(
                        value: 'delete',
                        height: 42,
                        child: Row(children: [
                          Icon(Icons.delete_outline_rounded, size: 17),
                          SizedBox(width: 8),
                          Text('删除', style: TextStyle(fontSize: 13)),
                        ])),
                  ],
                ),
              ),
            );
          },
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.project.name,
            style: const TextStyle(fontSize: 16.5)),
        actions: [
          IconButton(
            tooltip: '上传文档',
            icon: rag.uploading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.upload_file_outlined, size: 21),
            onPressed: rag.uploading ? null : _pickAndUpload,
          ),
          const SizedBox(width: 4),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'kb_upload',
        onPressed: rag.uploading ? null : _pickAndUpload,
        icon: const Icon(Icons.add_rounded, size: 20),
        label: const Text('上传文档', style: TextStyle(fontSize: 13)),
      ),
      body: body,
    );
  }

  Widget _statusChip(ColorScheme scheme, KbDocument d) {
    final Color color;
    final Widget child;
    switch (d.parseStatus) {
      case 'completed':
        color = const Color(0xFF2E7D32);
        child = Text('已完成', style: TextStyle(fontSize: 10.5, color: color));
      case 'parsing':
        color = const Color(0xFFB26A00);
        child = Row(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(
              width: 9,
              height: 9,
              child: CircularProgressIndicator(strokeWidth: 1.6, color: color)),
          const SizedBox(width: 4),
          Text('解析中', style: TextStyle(fontSize: 10.5, color: color)),
        ]);
      case 'failed':
        color = scheme.error;
        child = Text('失败', style: TextStyle(fontSize: 10.5, color: color));
      default:
        color = scheme.onSurfaceVariant;
        child = Text('待解析', style: TextStyle(fontSize: 10.5, color: color));
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(5),
      ),
      child: child,
    );
  }
}
