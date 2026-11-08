import 'package:flutter/material.dart';

import 'app.dart';
import 'common/app_core.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final core = await AppCore.create();
  runApp(CodeBiuApp(core: core));
}
