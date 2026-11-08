import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../types/kb_project.dart';
import '../providers/rag_provider.dart';
import 'kb_project_page.dart';

/// 知识库管理：项目列表（新建 / 重命名 / 删除 / 进入文档管理）
class KnowledgePage extends StatefulWidget {
  const KnowledgePage({super.key});

  @override
  State<KnowledgePage> createState() => _KnowledgePageState();
}

class _KnowledgePageState extends State<KnowledgePage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<RagProvider>().load();
    });
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _createDialog() async {
    final name = TextEditingController();
    final desc = TextEditingController();
    var category = 'project';
    var isPrivate = true;
    final err = await showDialog<String>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialog) => AlertDialog(
          title: const Text('新建知识库'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(
                    labelText: '名称 *', hintText: '例如：产品手册'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: desc,
                decoration: const InputDecoration(labelText: '描述'),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 6,
                children: [
                  for (final e in const [
                    ('personal', '个人'),
                    ('project', '项目'),
                    ('company', '公司'),
                  ])
                    ChoiceChip(
                      label: Text(e.$2, style: const TextStyle(fontSize: 12)),
                      selected: category == e.$1,
                      onSelected: (v) =>
                          setDialog(() => category = e.$1),
                    ),
                ],
              ),
              SwitchListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('私有（仅自己可见）',
                    style: TextStyle(fontSize: 13)),
                value: isPrivate,
                onChanged: (v) => setDialog(() => isPrivate = v),
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(ctx).pop(), child: const Text('取消')),
            FilledButton(
              onPressed: () {
                if (name.text.trim().isEmpty) return;
                Navigator.of(ctx).pop('ok');
              },
              child: const Text('创建'),
            ),
          ],
        ),
      ),
    );
    if (err == 'ok' && mounted) {
      final e2 = await context.read<RagProvider>().createProject(
            name: name.text.trim(),
            description: desc.text.trim(),
            kbCategory: category,
            isPrivate: isPrivate,
          );
      _toast(e2 ?? '知识库已创建');
    }
  }

  Future<void> _editDialog(KbProject p) async {
    final name = TextEditingController(text: p.name);
    final desc = TextEditingController(text: p.description ?? '');
    final err = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('编辑知识库'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: name, decoration: const InputDecoration(labelText: '名称 *')),
            const SizedBox(height: 12),
            TextField(controller: desc, decoration: const InputDecoration(labelText: '描述')),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(), child: const Text('取消')),
          FilledButton(
            onPressed: () {
              if (name.text.trim().isEmpty) return;
              Navigator.of(ctx).pop('ok');
            },
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (err == 'ok' && mounted) {
      final e2 = await context
          .read<RagProvider>()
          .renameProject(p, name.text.trim(), desc.text.trim());
      _toast(e2 ?? '已保存');
    }
  }

  Future<void> _confirmDelete(KbProject p) async {
    final scheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除知识库'),
        content: Text('将删除「${p.name}」及其全部文档与向量数据，不可恢复。'),
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
      final e2 = await context.read<RagProvider>().deleteProject(p.id);
      _toast(e2 ?? '已删除');
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final rag = context.watch<RagProvider>();

    Widget body;
    if (rag.loading && rag.projects.isEmpty) {
      body = const Center(
          child: CircularProgressIndicator(strokeWidth: 2.4));
    } else if (rag.error != null && rag.projects.isEmpty) {
      body = _centerMessage(
          context, Icons.cloud_off_rounded, rag.error!, retry: true);
    } else if (rag.projects.isEmpty) {
      body = _centerMessage(context, Icons.folder_open_rounded,
          '还没有知识库\n点击右上角「+」创建第一个');
    } else {
      body = RefreshIndicator(
        onRefresh: () => context.read<RagProvider>().load(),
        child: ListView.separated(
          padding: const EdgeInsets.all(12),
          itemCount: rag.projects.length,
          separatorBuilder: (_, _) => const SizedBox(height: 8),
          itemBuilder: (_, i) {
            final p = rag.projects[i];
            return Card(
              child: ListTile(
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                leading: Container(
                  width: 38,
                  height: 38,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: scheme.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.menu_book_outlined,
                      size: 19, color: scheme.primary),
                ),
                title: Text(p.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 14.5, fontWeight: FontWeight.w600)),
                subtitle: Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Row(
                    children: [
                      _tag(scheme, p.categoryLabel, scheme.primary),
                      const SizedBox(width: 5),
                      if (p.isPrivate)
                        _tag(scheme, '私有', scheme.onSurfaceVariant),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          p.description ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontSize: 11.5,
                              color: scheme.onSurfaceVariant),
                        ),
                      ),
                    ],
                  ),
                ),
                trailing: PopupMenuButton<String>(
                  icon: Icon(Icons.more_vert_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  onSelected: (a) {
                    if (a == 'rename') {
                      _editDialog(p);
                    } else if (a == 'delete') {
                      _confirmDelete(p);
                    }
                  },
                  itemBuilder: (_) => const [
                    PopupMenuItem(
                        value: 'rename',
                        height: 42,
                        child: Row(children: [
                          Icon(Icons.edit_outlined, size: 17),
                          SizedBox(width: 8),
                          Text('编辑', style: TextStyle(fontSize: 13)),
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
                onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                    builder: (_) => KbProjectPage(project: p))),
              ),
            );
          },
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('知识库'),
        actions: [
          IconButton(
            tooltip: '新建知识库',
            icon: const Icon(Icons.add_rounded, size: 22),
            onPressed: _createDialog,
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: body,
    );
  }

  Widget _centerMessage(BuildContext context, IconData icon, String text,
      {bool retry = false}) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 42, color: scheme.onSurfaceVariant),
          const SizedBox(height: 12),
          Text(text,
              textAlign: TextAlign.center,
              style:
                  TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
          if (retry) ...[
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: () => context.read<RagProvider>().load(),
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('重试', style: TextStyle(fontSize: 13)),
            ),
          ],
        ],
      ),
    );
  }

  Widget _tag(ColorScheme scheme, String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 10.5, color: color, fontWeight: FontWeight.w600)),
    );
  }
}
