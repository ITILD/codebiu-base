# flutter 客户端 — AI 协作规则（客户端分层）

> 全局工作流（需求 → 批准 → 开发 → 交付）见根 [README_AI.md](../../../README_AI.md)；本文件只约束 Flutter 客户端代码与文档；后端规则见 [server_py/README_AI.md](../../backend/server_py/README_AI.md)；Web 前端规则见 [vue3/README_AI.md](../vue3/README_AI.md)；文档导航见 [doc/README.md](doc/README.md)。

## 1. 修改前必读

1. 功能在根 [需求功能登记册](../../../doc/02-设计文档/00-需求功能登记册.md) 为「已批准」（缺陷/文档/纯重构/依赖升级豁免）。
2. 先读 [01-开发指南](doc/dev/01-开发指南.md)，确认改动落在哪一层（ui → providers → services → models）。
3. 写代码前读 [02-代码规范](doc/dev/02-代码规范.md)（12 条硬规则）。
4. 任务拆解与验收按 [03-新成员与AI协作指南](doc/dev/03-新成员与AI协作指南.md) 第 4~6 节执行。

## 2. 硬规则（客户端）

1. **四层单向依赖**：`ui → providers → core/services → core/models`；`ui/` 禁 import dio 与 SharedPreferences，`providers/` 禁 import material.dart，`core/` 禁 import 上层。
2. **页面无业务**：页面只取状态、调 provider 动作方法、展示 `apiErrorMessage` 中文化的错误。
3. **HTTP 统一走 Service**：所有请求经 `AppCore.dio`（自动 Bearer/401 刷新重放）；一个后端域一个 Service 类，路径常量置顶。
4. **令牌链路集中**：认证/刷新/登出逻辑只在 `auth_interceptor.dart` 与 `auth_service.dart`；他处禁止手动拼 Authorization 头。
5. **SSE 协议集中**：流式解析只在 `ai_service.dart`；后端协议变更只改该文件并同步本目录文档。
6. **状态只用 provider**：ChangeNotifier + watch/read；跨页共享状态进 `providers/`，禁止页面级全局变量。
7. **主题与尺寸**：颜色一律 colorScheme；宽屏限宽交给 `PhoneShell`，页面禁止自建 maxWidth 逻辑。
8. **平台壳三处同步**：桌面窗口尺寸/应用名改动必须 linux/windows/macos 同步；Android/iOS 网络与明文传输配置不得删除。
9. **依赖白名单**：`dio`、`provider`、`shared_preferences`、`flutter_localizations`、`file_picker`（文档上传）；新增需登记理由，禁止引入 UI 组件库/路由库/新状态库。
10. **中文文案**：界面与错误提示全部中文；`flutter analyze` 0 issue（含 info）为完成门槛。

## 3. 典型改动清单

| 改动 | 必做 |
| :--- | :--- |
| 新增页面 | `ui/pages/*.dart`；挂入口（home_page 导航或 Navigator.push）；双主题+宽屏验收 |
| 新增后端能力 | models（+单测）→ service 方法 → provider 动作 → 页面调用；错误中文化 |
| 改登录/注册 | 读 `auth_interceptor.dart`；回归 401 刷新与登出吊销链路 |
| 改 AI 对话 | 只动 `ai_service.dart`/`chat_provider.dart`；本地模式规则改 `local_assistant.dart`（带单测） |
| 改主题 | `ui/theme.dart` 单点修改；亮暗两套同时验收 |
| 改窗口/应用名 | linux/windows/macos 三处同步（见开发指南 5.3） |
| 依赖变更 | `pubspec.yaml` + 提交说明登记理由 + analyze/test/build 全过 |

## 4. 验证命令

```bash
cd code/frontend/flutter
flutter analyze            # 必须 0 issue
flutter test               # 全部通过
flutter build linux --release   # 桌面编译（改平台代码时必跑）
flutter build apk --debug      # Android 编译（改依赖/平台代码时跑）
```

提交前至少保证 `flutter analyze` + `flutter test` 通过；分层越界检查：
`grep -r "dio" lib/ui lib/providers` 与 `grep -r "material.dart" lib/providers` 必须无命中。
