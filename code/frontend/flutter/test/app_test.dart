import 'package:flutter_test/flutter_test.dart';

import 'package:codebiu/core/services/local_assistant.dart';

void main() {
  group('LocalAssistant', () {
    test('问候语回复', () {
      final reply = LocalAssistant.reply('你好');
      expect(reply.contains('你好'), isTrue);
    });

    test('数学计算', () {
      final reply = LocalAssistant.reply('(128+64)/8*2.5');
      expect(reply.contains('60'), isTrue);
    });

    test('非算术输入不误判', () {
      expect(LocalAssistant.reply('你好'), isNot(contains('=')));
    });
  });
}
