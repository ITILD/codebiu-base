import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'core/app_core.dart';
import 'core/settings.dart';
import 'providers/agent_provider.dart';
import 'providers/auth_provider.dart';
import 'providers/chat_provider.dart';
import 'providers/rag_provider.dart';
import 'ui/pages/auth_gate.dart';
import 'ui/theme.dart';

/// 应用根组件
class CodeBiuApp extends StatelessWidget {
  const CodeBiuApp({super.key, required this.core});

  final AppCore core;

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<AppSettings>.value(value: core.settings),
        ChangeNotifierProvider(
          create: (_) => AuthProvider(core)..bootstrap(),
        ),
        ChangeNotifierProvider(create: (_) => ChatProvider(core)),
        ChangeNotifierProvider(create: (_) => RagProvider(core)),
        ChangeNotifierProvider(create: (_) => AgentProvider(core)),
      ],
      child: ListenableBuilder(
        listenable: core.settings,
        builder: (context, _) {
          final settings = core.settings;
          return MaterialApp(
            title: 'CodeBiu',
            debugShowCheckedModeBanner: false,
            theme: AppTheme.light(),
            darkTheme: AppTheme.dark(),
            themeMode: settings.themeMode,
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [Locale('zh'), Locale('en')],
            builder: (context, child) =>
                PhoneShell(child: child ?? const SizedBox.shrink()),
            home: const AuthGate(),
          );
        },
      ),
    );
  }
}
