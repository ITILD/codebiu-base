import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/chat_provider.dart';

/// 在线模型选择页（数据来自后端 /ai/model-configs）
class ModelPickerPage extends StatefulWidget {
  const ModelPickerPage({super.key});

  @override
  State<ModelPickerPage> createState() => _ModelPickerPageState();
}

class _ModelPickerPageState extends State<ModelPickerPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<ChatProvider>().loadModels();
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final chat = context.watch<ChatProvider>();
    final currentId = chat.currentModel?.id;

    Widget body;
    if (chat.modelsLoading && chat.models.isEmpty) {
      body = const Center(child: CircularProgressIndicator(strokeWidth: 2.4));
    } else if (chat.modelsError != null && chat.models.isEmpty) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded,
                size: 40, color: scheme.onSurfaceVariant),
            const SizedBox(height: 12),
            Text(chat.modelsError!,
                textAlign: TextAlign.center,
                style:
                    TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: () => context.read<ChatProvider>().loadModels(),
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('重试', style: TextStyle(fontSize: 13)),
            ),
          ],
        ),
      );
    } else if (chat.models.isEmpty) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.inbox_outlined, size: 40, color: scheme.onSurfaceVariant),
            const SizedBox(height: 12),
            const Text('暂无可用模型',
                style: TextStyle(fontSize: 13.5)),
            const SizedBox(height: 6),
            Text('请联系管理员在后台配置 chat 类模型',
                style:
                    TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          ],
        ),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: () => context.read<ChatProvider>().loadModels(),
        child: ListView.separated(
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
          itemCount: chat.models.length,
          separatorBuilder: (_, _) => const SizedBox(height: 6),
          itemBuilder: (_, i) {
            final m = chat.models[i];
            final selected = m.id == currentId;
            final disabled = !m.isActive;
            return Opacity(
              opacity: disabled ? 0.55 : 1,
              child: ListTile(
                onTap: disabled
                    ? null
                    : () {
                        context.read<ChatProvider>().selectModel(m.id);
                        Navigator.of(context).pop();
                      },
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                  side: BorderSide(
                    color: selected
                        ? scheme.primary
                        : Colors.transparent,
                    width: 1.4,
                  ),
                ),
                tileColor: selected
                    ? scheme.primary.withValues(alpha: 0.06)
                    : scheme.surface,
                leading: Icon(
                  selected
                      ? Icons.check_circle_rounded
                      : Icons.radio_button_unchecked_rounded,
                  size: 20,
                  color: selected
                      ? scheme.primary
                      : scheme.onSurfaceVariant,
                ),
                title: Text(m.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight:
                            selected ? FontWeight.w600 : FontWeight.w500,
                        color: disabled ? scheme.onSurfaceVariant : null)),
                subtitle: Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    '${m.model} · ${m.serverType}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 11.5, color: scheme.onSurfaceVariant),
                  ),
                ),
                trailing: Wrap(
                  spacing: 5,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    if (m.isDefault)
                      _tag(scheme, '默认', scheme.primary),
                    if (disabled)
                      _tag(scheme, '停用', scheme.onSurfaceVariant)
                    else if (m.checkValid == true)
                      _tag(scheme, '可用', Color(0xFF2E7D32)),
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
        title: const Text('选择模型'),
        actions: [
          IconButton(
            tooltip: '刷新',
            icon: const Icon(Icons.refresh_rounded, size: 20),
            onPressed: () => context.read<ChatProvider>().loadModels(),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: body,
    );
  }

  Widget _tag(ColorScheme scheme, String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
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
