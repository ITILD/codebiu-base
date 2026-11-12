import 'package:flutter/foundation.dart';

import '../../../common/app_core.dart';
import '../api/agent_service.dart';
import '../../../common/services/api_error.dart';

/// 智能体配置状态：Agent 列表 + 技能注册表
class AgentProvider extends ChangeNotifier {
  AgentProvider(this._core);

  final AppCore _core;

  List<AgentInfo> agents = <AgentInfo>[];
  List<AgentSkill> skills = <AgentSkill>[];
  bool loading = false;
  String? error;

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final results = await Future.wait<dynamic>([
        _core.agent.agents(),
        _core.agent.skills(),
      ]);
      agents = results[0] as List<AgentInfo>;
      skills = results[1] as List<AgentSkill>;
    } catch (e) {
      error = apiErrorMessage(e);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  /// 技能值显示名：注册表内按全局键取展示名；旧短名（不含 "."）等未知值原样返回
  String skillLabel(String value) {
    for (final s in skills) {
      if (s.key == value) return s.name;
    }
    return value;
  }

  Future<String?> create(AgentInfo agent) async {
    try {
      await _core.agent.create(agent);
      await load();
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  Future<String?> update(String id, AgentInfo agent) async {
    try {
      await _core.agent.update(id, agent);
      await load();
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }

  Future<String?> delete(String id) async {
    try {
      await _core.agent.delete(id);
      await load();
      return null;
    } catch (e) {
      return apiErrorMessage(e);
    }
  }
}
