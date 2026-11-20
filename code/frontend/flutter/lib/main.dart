import 'package:flutter/material.dart';

import 'app.dart';
import 'common/app_core.dart';

// @doc-sync: code/frontend/flutter/doc/dev/01-开发指南.md; doc/02-设计文档/04-AI能力平台架构设计.md
// 触发: 客户端入口/组合根/能力入口变化时，同步上述文档与 doc/doc-manifest.yaml

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final core = await AppCore.create();
  runApp(CodeBiuApp(core: core));
}
