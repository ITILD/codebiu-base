import 'dart:math' as math;

/// 本地离线 AI 助手（无需联网/服务器）：基于规则的轻量应答引擎
///
/// 支持问候、自我介绍、时间日期、四则运算、笑话、使用帮助与通用兜底，
/// 回复通过打字机效果在 ChatProvider 中流式呈现。
class LocalAssistant {
  LocalAssistant._();

  static final _jokes = [
    '程序员最讨厌的两件事：一是别人不写注释，二是别人让自己写注释。',
    '为什么程序员总把万圣节和圣诞节搞混？因为 Oct 31 == Dec 25。',
    '世界上最远的距离，是我在 if 里，你在 else 里。',
    '客户说“这个需求很简单”，于是程序员加班到了凌晨三点。',
    '重启一下试试？—— IT 界的万能咒语。',
  ];

  static final _random = math.Random();

  /// 生成回复
  static String reply(String input, {DateTime? now}) {
    final text = input.trim();
    final t = now ?? DateTime.now();

    if (text.isEmpty) {
      return '想说点什么？可以直接输入问题，也可以输入“帮助”查看我能做什么。';
    }

    // 数学运算优先（形如 "3+5*2"、"计算 (12+8)/5"）
    final mathResult = _tryMath(text);
    if (mathResult != null) return mathResult;

    final lower = text.toLowerCase();

    if (_hit(text, ['你好', '您好', '嗨', '哈喽']) ||
        lower == 'hi' || lower == 'hello' || lower == 'hey') {
      return '你好！我是 CodeBiu 内置的本地助手，无需联网即可使用。'
          '你可以问我时间日期、让我算个数学题，或输入“帮助”查看全部功能。';
    }

    if (_hit(text, ['你是谁', '自我介绍', '介绍一下', '你叫什么'])) {
      return '我是 CodeBiu 客户端内置的本地 AI 助手，完全运行在你的设备上，离线可用。'
          '我擅长简单问答、时间日期查询和数学计算。如果需要更强的能力（长文写作、代码、联网知识），'
          '可以在右上角菜单切换到“在线模式”，调用服务器上的大模型。';
    }

    if (_hit(text, ['帮助', 'help', '功能', '能做什么', '你会什么', '怎么用'])) {
      return '我目前支持这些能力：\n'
          '1. 数学计算：例如 (128+64)/8*2.5\n'
          '2. 时间查询：现在几点\n'
          '3. 日期查询：今天几号、星期几\n'
          '4. 讲个笑话\n'
          '5. 闲聊与简单问答\n\n'
          '需要联网调用大模型时，请切换到“在线模式”。';
    }

    if (_hit(text, ['几点', '时间', 'now'])) {
      final h = t.hour.toString().padLeft(2, '0');
      final m = t.minute.toString().padLeft(2, '0');
      return '现在是 $h:$m（${t.hour} 点 ${t.minute} 分）。';
    }

    if (_hit(text, ['几号', '日期', '星期', '今天是'])) {
      const weeks = ['一', '二', '三', '四', '五', '六', '日'];
      final y = t.year;
      final mo = t.month.toString().padLeft(2, '0');
      final d = t.day.toString().padLeft(2, '0');
      return '今天是 $y 年 $mo 月 $d 日，星期${weeks[t.weekday - 1]}。';
    }

    if (_hit(text, ['笑话', '段子', '幽默'])) {
      return _jokes[_random.nextInt(_jokes.length)];
    }

    if (_hit(text, ['谢谢', '感谢', '多谢'])) {
      return '不客气，能帮到你就好。还有其他问题吗？';
    }

    if (_hit(text, ['再见', '拜拜', '晚安', 'bye'])) {
      return '再见！我随时都在，离线也可以找到我。';
    }

    if (_hit(text, ['在线', '切换', '服务器', '大模型', 'model', '联网'])) {
      return '切换方式：点击聊天页右上角的菜单按钮，选择“切换模式”，即可在“在线 / 本地”之间切换。\n'
          '- 在线模式：调用后端服务器配置的大模型，能力更强；\n'
          '- 本地模式：完全离线运行，隐私安全、随时可用。';
    }

    // 疑问句兜底：给出引导式回答
    if (text.endsWith('吗') ||
        _hit(text, ['怎么', '为什么', '如何', '什么是', '什么是', '介绍', '推荐'])) {
      return '这是个好问题。不过本地模式能力有限，主要提供数学计算、时间日期查询与日常问答。\n'
          '关于“$text”，建议你：\n'
          '1. 切换到在线模式，让服务器端的大模型详细解答；\n'
          '2. 或者把问题拆解成更具体的计算/查询类小问题，我可以直接帮你算。';
    }

    // 通用兜底
    return '收到你的消息：“$text”。\n'
        '本地模式更擅长计算与查询，例如输入 99*37+1024 立刻得到结果；\n'
        '需要深入交流或生成内容时，建议切换到在线模式体验完整的大模型能力。';
  }

  static bool _hit(String text, List<String> keys) {
    for (final k in keys) {
      if (text.contains(k)) return true;
    }
    return false;
  }

  /// 尝试解析并计算算术表达式；不是算式返回 null
  static String? _tryMath(String input) {
    var s = input
        .replaceAll('×', '*')
        .replaceAll('÷', '/')
        .replaceAll('（', '(')
        .replaceAll('）', ')')
        .replaceAll('，', '')
        .replaceAll(',', '')
        .replaceAll('＝', '=');
    s = s.replaceFirst(RegExp(r'^(计算|算一下|算一算|帮我算)'), '').trim();
    s = s.replaceFirst(RegExp(r'=?\s*$'), '').trim();
    if (s.isEmpty) return null;
    if (!RegExp(r'^[\d\s+\-*/().%^]+$').hasMatch(s)) return null;
    if (!RegExp(r'\d').hasMatch(s) || !RegExp(r'[+\-*/^%]').hasMatch(s)) {
      return null;
    }
    try {
      final v = _MathParser(s).parse();
      if (v.isNaN || v.isInfinite) return null;
      String out;
      if (v == v.roundToDouble()) {
        out = v.toInt().toString();
      } else {
        out = v.toStringAsFixed(6).replaceFirst(RegExp(r'0+$'), '');
        out = out.replaceFirst(RegExp(r'\.$'), '');
      }
      return '$s = $out';
    } catch (_) {
      return null;
    }
  }
}

/// 递归下降算术表达式解析器（支持 + - * / % ^ 与括号、一元正负号）
class _MathParser {
  _MathParser(this._s);

  final String _s;
  int _i = 0;

  double parse() {
    final v = _expr();
    _ws();
    if (_i != _s.length) throw const FormatException('表达式不完整');
    return v;
  }

  void _ws() {
    while (_i < _s.length && _s.codeUnitAt(_i) == 0x20) {
      _i++;
    }
  }

  double _expr() {
    var v = _term();
    while (true) {
      _ws();
      if (_i < _s.length && (_s[_i] == '+' || _s[_i] == '-')) {
        final op = _s[_i++];
        final r = _term();
        v = op == '+' ? v + r : v - r;
      } else {
        return v;
      }
    }
  }

  double _term() {
    var v = _unary();
    while (true) {
      _ws();
      if (_i < _s.length &&
          (_s[_i] == '*' || _s[_i] == '/' || _s[_i] == '%')) {
        final op = _s[_i++];
        final r = _unary();
        v = op == '*' ? v * r : (op == '/' ? v / r : v % r);
      } else {
        return v;
      }
    }
  }

  double _unary() {
    _ws();
    if (_i < _s.length && _s[_i] == '-') {
      _i++;
      return -_unary();
    }
    if (_i < _s.length && _s[_i] == '+') {
      _i++;
      return _unary();
    }
    return _power();
  }

  double _power() {
    final base = _atom();
    _ws();
    if (_i < _s.length && _s[_i] == '^') {
      _i++;
      return math.pow(base, _unary()).toDouble();
    }
    return base;
  }

  double _atom() {
    _ws();
    if (_i < _s.length && _s[_i] == '(') {
      _i++;
      final v = _expr();
      _ws();
      if (_i >= _s.length || _s[_i] != ')') {
        throw const FormatException('括号不匹配');
      }
      _i++;
      return v;
    }
    final start = _i;
    while (_i < _s.length &&
        (_s[_i].contains(RegExp(r'[\d.]')))) {
      _i++;
    }
    if (start == _i) throw const FormatException('缺少数字');
    return double.parse(_s.substring(start, _i));
  }
}
