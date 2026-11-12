import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/agent_service.dart';
import '../providers/agent_provider.dart';

/// 智能体配置：列表 / 新建 / 编辑（提示词 + 技能）/ 删除
class AgentPage extends StatefulWidget {
  const AgentPage({super.key});

  @override
  State<AgentPage> createState() => _AgentPageState();
}

class _AgentPageState extends State<AgentPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<AgentProvider>().load();
    });
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _editSheet([AgentInfo? agent]) async {
    final name = TextEditingController(text: agent?.name ?? '');
    final desc = TextEditingController(text: agent?.description ?? '');
    final prompt = TextEditingController(text: agent?.defaultPrompt ?? '');
    final skills = <String>{...?agent?.skills};
    var isPublic = agent?.isPublic ?? false;
    final provider = context.read<AgentProvider>();

    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => Padding(
          padding: EdgeInsets.only(
              left: 20, right: 20,
              bottom: MediaQuery.of(ctx).viewInsets.bottom + 16),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(agent == null ? '新建智能体' : '编辑智能体',
                    style: Theme.of(ctx)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 14),
                TextField(
                  controller: name,
                  decoration: const InputDecoration(
                      labelText: '名称 *', hintText: '例如：翻译助手'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: desc,
                  decoration: const InputDecoration(labelText: '描述'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: prompt,
                  maxLines: 4,
                  minLines: 3,
                  decoration: const InputDecoration(
                    labelText: '系统提示词',
                    hintText: '设定助手的角色与回答风格',
                    alignLabelWithHint: true,
                  ),
                ),
                const SizedBox(height: 12),
                if (provider.skills.isNotEmpty) ...[
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text('技能',
                        style: TextStyle(
                            fontSize: 12.5,
                            color: Theme.of(ctx).colorScheme.onSurfaceVariant)),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final s in provider.skills)
                        FilterChip(
                          label: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(s.name,
                                  style: const TextStyle(fontSize: 12)),
                              if (_natureLabel(s.nature) != null) ...[
                                const SizedBox(width: 5),
                                _natureBadge(
                                    s.nature, Theme.of(ctx).colorScheme),
                              ],
                            ],
                          ),
                          selected: skills.contains(s.key),
                          onSelected: s.agentCallable
                              ? (v) => setSheet(() {
                                    v ? skills.add(s.key) : skills.remove(s.key);
                                  })
                              : null,
                        ),
                      // 存量旧短名（不含 "."）等注册表外的已存值：原样回显，可移除
                      for (final v in skills
                          .where((v) =>
                              !provider.skills.any((s) => s.key == v))
                          .toList())
                        InputChip(
                          label: Text(v, style: const TextStyle(fontSize: 12)),
                          onDeleted: () =>
                              setSheet(() => skills.remove(v)),
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                ],
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('公开（所有人可用）',
                      style: TextStyle(fontSize: 13)),
                  value: isPublic,
                  onChanged: (v) => setSheet(() => isPublic = v),
                ),
                const SizedBox(height: 8),
                FilledButton(
                  onPressed: name.text.trim().isEmpty
                      ? null
                      : () => Navigator.of(ctx).pop(true),
                  child: Text(agent == null ? '创建' : '保存'),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    if (ok != true) return;
    final data = AgentInfo(
      id: agent?.id ?? '',
      name: name.text.trim(),
      description: desc.text.trim(),
      defaultPrompt: prompt.text.trim(),
      defaultProjectIds: agent?.defaultProjectIds ?? const [],
      skills: skills.toList(),
      isPublic: isPublic,
      isBuiltin: agent?.isBuiltin ?? false,
      ownerUserId: agent?.ownerUserId,
    );
    final err = agent == null
        ? await provider.create(data)
        : await provider.update(agent.id, data);
    if (mounted) _toast(err ?? (agent == null ? '智能体已创建' : '已保存'));
  }

  Future<void> _confirmDelete(AgentInfo a) async {
    final scheme = Theme.of(context).colorScheme;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除智能体'),
        content: Text('将删除「${a.name}」。'),
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
      final err = await context.read<AgentProvider>().delete(a.id);
      if (mounted) _toast(err ?? '已删除');
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final provider = context.watch<AgentProvider>();

    Widget body;
    if (provider.loading && provider.agents.isEmpty) {
      body = const Center(
          child: CircularProgressIndicator(strokeWidth: 2.4));
    } else if (provider.error != null && provider.agents.isEmpty) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded,
                size: 40, color: scheme.onSurfaceVariant),
            const SizedBox(height: 10),
            Text(provider.error!,
                style: TextStyle(
                    fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => context.read<AgentProvider>().load(),
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('重试', style: TextStyle(fontSize: 13)),
            ),
          ],
        ),
      );
    } else if (provider.agents.isEmpty) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.auto_awesome_rounded,
                size: 42, color: scheme.onSurfaceVariant),
            const SizedBox(height: 12),
            const Text('还没有智能体', style: TextStyle(fontSize: 13.5)),
            const SizedBox(height: 6),
            Text('点击右下角创建你的专属助手',
                style: TextStyle(
                    fontSize: 12, color: scheme.onSurfaceVariant)),
          ],
        ),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: () => context.read<AgentProvider>().load(),
        child: ListView.separated(
          padding: const EdgeInsets.all(12),
          itemCount: provider.agents.length,
          separatorBuilder: (_, _) => const SizedBox(height: 8),
          itemBuilder: (_, i) {
            final a = provider.agents[i];
            return Card(
              child: ListTile(
                leading: Container(
                  width: 38,
                  height: 38,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: scheme.primary.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.auto_awesome_rounded,
                      size: 19, color: scheme.primary),
                ),
                title: Row(
                  children: [
                    Flexible(
                      child: Text(a.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 14.5, fontWeight: FontWeight.w600)),
                    ),
                    if (a.agentKind == 'job') ...[
                      const SizedBox(width: 6),
                      _tag(scheme, '任务', scheme.tertiary),
                    ],
                    if (a.isBuiltin) ...[
                      const SizedBox(width: 6),
                      _tag(scheme, '内置', scheme.onSurfaceVariant),
                    ] else if (a.isPublic) ...[
                      const SizedBox(width: 6),
                      _tag(scheme, '公开', scheme.primary),
                    ],
                  ],
                ),
                subtitle: Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Text(
                    a.skills.isEmpty
                        ? (a.description ?? '—')
                        : '技能：${a.skills.map(provider.skillLabel).join(' / ')}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 11.5, color: scheme.onSurfaceVariant),
                  ),
                ),
                trailing: a.isBuiltin
                    ? null
                    : PopupMenuButton<String>(
                        icon: Icon(Icons.more_vert_rounded,
                            size: 18, color: scheme.onSurfaceVariant),
                        onSelected: (act) {
                          if (act == 'edit') {
                            _editSheet(a);
                          } else if (act == 'delete') {
                            _confirmDelete(a);
                          }
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(
                              value: 'edit',
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
                onTap: a.isBuiltin ? null : () => _editSheet(a),
              ),
            );
          },
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('智能体配置')),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'agent_create',
        onPressed: () => _editSheet(),
        icon: const Icon(Icons.add_rounded, size: 20),
        label: const Text('新建', style: TextStyle(fontSize: 13)),
      ),
      body: body,
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

  /// 技能实现性质徽标文案：static=规则 / ai=模型 / hybrid=混合
  String? _natureLabel(String nature) => switch (nature) {
        'static' => '规则',
        'ai' => '模型',
        'hybrid' => '混合',
        _ => null,
      };

  Widget _natureBadge(String nature, ColorScheme scheme) {
    final label = _natureLabel(nature);
    if (label == null) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
      decoration: BoxDecoration(
        color: scheme.onSurfaceVariant.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: 9.5,
              color: scheme.onSurfaceVariant,
              fontWeight: FontWeight.w600)),
    );
  }
}
