import 'package:flutter/material.dart';

import 'app.dart';
import 'core/app_core.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final core = await AppCore.create();
  runApp(CodeBiuApp(core: core));
}
