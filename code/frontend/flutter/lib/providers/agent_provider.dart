import 'package:flutter/foundation.dart';

import '../core/app_core.dart';
import '../core/services/agent_service.dart';
import '../core/services/api_error.dart';

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
