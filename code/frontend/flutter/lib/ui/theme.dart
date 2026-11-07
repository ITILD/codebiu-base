import 'package:flutter/material.dart';

import '../core/constants.dart';

/// 主题：与 Web 端「自然笔记」风格同源（vue3 base.css --note-* 令牌），
/// 保留手机端紧凑 SaaS 特色
class AppTheme {
  AppTheme._();

  /// 主色：Web 端 --note-green #2E7C6B（青绿）
  static const Color seedColor = Color(0xFF2E7C6B);

  /// 亮色纸面：--note-paper #EFF3F1；暗色纸面：--note-paper(dark) #0D1319
  static const Color lightScaffold = Color(0xFFEFF3F1);
  static const Color darkScaffold = Color(0xFF0D1319);

  /// 卡片/描边（--note-card / --note-border）
  static const Color darkCard = Color(0xFF1A232C);
  static const Color lightBorder = Color(0xFFD8E1DD);
  static const Color darkBorder = Color(0xFF2E3B47);

  static ThemeData light() {
    final scheme = ColorScheme.fromSeed(
      seedColor: seedColor,
      brightness: Brightness.light,
    );
    return _base(
      scheme.copyWith(
        surface: Colors.white,
        surfaceContainerLowest: Colors.white,
        outlineVariant: lightBorder,
        onSurfaceVariant: const Color(0xFF5F6F76), // --note-sub
      ),
      lightScaffold,
    );
  }

  static ThemeData dark() {
    // 暗色主色提亮：--note-green(dark) #38A487，保证深底对比度
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF38A487),
      brightness: Brightness.dark,
    );
    return _base(
      scheme.copyWith(
        surface: darkCard,
        surfaceContainerLowest: darkCard,
        outlineVariant: darkBorder,
      ),
      darkScaffold,
    );
  }

  static ThemeData _base(ColorScheme scheme, Color scaffold) {
    final outline = OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: BorderSide(color: scheme.outlineVariant, width: 1),
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scaffold,
      visualDensity: VisualDensity.compact,
      splashFactory: InkSparkle.splashFactory,
      appBarTheme: AppBarTheme(
        backgroundColor: scaffold,
        foregroundColor: scheme.onSurface,
        surfaceTintColor: Colors.transparent,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontSize: 17,
          fontWeight: FontWeight.w700,
          color: scheme.onSurface,
        ),
        actionsIconTheme: IconThemeData(color: scheme.onSurfaceVariant),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: outline,
        enabledBorder: outline,
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: scheme.primary, width: 1.6),
        ),
        errorBorder: outline,
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: scheme.error, width: 1.6),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        hintStyle: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(46),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      cardTheme: CardThemeData(
        color: scheme.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side:
              BorderSide(color: scheme.outlineVariant.withValues(alpha: 0.6)),
        ),
      ),
      listTileTheme: ListTileThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        iconColor: scheme.primary,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          visualDensity: VisualDensity.compact,
          shape: const WidgetStatePropertyAll(
            RoundedRectangleBorder(
              borderRadius: BorderRadius.all(Radius.circular(8)),
            ),
          ),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
      dividerTheme: DividerThemeData(
        color: scheme.outlineVariant.withValues(alpha: 0.5),
        thickness: 0.8,
        space: 0.8,
      ),
      popupMenuTheme: PopupMenuThemeData(
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}

/// 桌面端手机宽度外壳：宽屏时内容居中并限制最大宽度
class PhoneShell extends StatelessWidget {
  const PhoneShell({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width <= AppConstants.phoneMaxWidth + 8) {
      return child;
    }
    final bg = Theme.of(context).scaffoldBackgroundColor;
    return ColoredBox(
      color: bg.withValues(alpha: 0.35),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: AppConstants.phoneMaxWidth,
          ),
          child: child,
        ),
      ),
    );
  }
}
