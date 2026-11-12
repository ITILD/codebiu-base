import 'package:flutter_test/flutter_test.dart';

import 'package:codebiu/modules/agent/api/agent_service.dart';

void main() {
  group('AgentSkill.fromJson（REQ-018 Manifest 视图）', () {
    test('解析全局键/展示名/性质/可对话调用', () {
      final s = AgentSkill.fromJson({
        'key': 'sys.web_search',
        'name': '网络搜索',
        'description': '联网检索',
        'category': 'search',
        'skill_type': 'builtin',
        'nature': 'hybrid',
        'version': '2',
        'side_effects': 'none',
        'agent_callable': true,
        'capabilities': {
          'required': ['web'],
          'optional': [],
          'alternatives': <String, dynamic>{},
        },
        'execution': <String, dynamic>{'mode': 'auto'},
        'input_schema': <String, dynamic>{},
        'output_schema': <String, dynamic>{},
      });
      expect(s.key, 'sys.web_search');
      expect(s.name, '网络搜索');
      expect(s.nature, 'hybrid');
      expect(s.agentCallable, isTrue);
    });

    test('不可对话调用与缺省字段容错', () {
      final s = AgentSkill.fromJson({
        'key': 'sys.doc_parse',
        'agent_callable': false,
      });
      expect(s.agentCallable, isFalse);
      expect(s.name, 'sys.doc_parse'); // 缺展示名时回退全局键
      expect(s.nature, '');
    });
  });

  group('AgentInfo.fromJson（新增形态/决策字段）', () {
    test('解析 agent_kind/decision_mode', () {
      final a = AgentInfo.fromJson({
        'id': 'a1',
        'name': '编排助手',
        'agent_kind': 'job',
        'decision_mode': 'rule',
      });
      expect(a.agentKind, 'job');
      expect(a.decisionMode, 'rule');
    });

    test('旧响应缺新字段时取默认 chat/model', () {
      final a = AgentInfo.fromJson({'id': 'a2', 'name': '聊天助手'});
      expect(a.agentKind, 'chat');
      expect(a.decisionMode, 'model');
    });
  });
}
