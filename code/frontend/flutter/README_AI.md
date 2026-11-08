# flutter 客户端 — AI 协作规则（客户端分层）

> 全局工作流（需求 → 批准 → 开发 → 交付）见根 [README_AI.md](../../../README_AI.md)；本文件只约束 Flutter 客户端代码与文档；后端规则见 [server_py/README_AI.md](../../backend/server_py/README_AI.md)；Web 前端规则见 [vue3/README_AI.md](../vue3/README_AI.md)；文档导航见 [doc/README.md](doc/README.md)。

## 1. 修改前必读

1. 功能在根 [需求功能登记册](../../../doc/02-设计文档/00-需求功能登记册.md) 为「已批准」（缺陷/文档/纯重构/依赖升级豁免）。
2. 先读 [01-开发指南](doc/dev/01-开发指南.md)，确认改动落在哪个模块的哪一层（`pages → providers → api → types`）。
3. 写代码前读 [02-代码规范](doc/dev/02-代码规范.md)（12 条硬规则）。
4. 任务拆解与验收按 [03-新成员与AI协作指南](doc/dev/03-新成员与AI协作指南.md) 第 4~6 节执行。

## 2. 硬规则（客户端）

1. **目录即模块**：业务代码一律放 `lib/modules/<模块>/{api,types,providers,pages}`，模块名与后端 `src/module_*` 和 `vue3/src/modules/*` 同名（`authorization`/`ai`/`agent`/`rag`）；跨模块基础设施放 `lib/common/`。不建空模块、不建空目录。
2. **四层单向依赖**：`pages → providers → api → types`；`pages/` 禁 import dio 与 SharedPreferences（唯一例外：设置页「测试连接」用临时 Dio 探测新地址），`providers/` 禁 import material.dart，`api/` 与 `types/` 不依赖上层。`common/` 不得 import 任何 `modules/*/pages` 或 `modules/*/providers`（`common/app_core.dart` 是唯一组合根，可装配各模块 `api`）。
3. **页面无业务**：页面只取状态、调 provider 动作方法、展示 `apiErrorMessage` 中文化的错误。
4. **HTTP 统一走 api 层**：所有请求经 `AppCore.dio`（自动 Bearer/401 刷新重放）；一个后端域一个 Service 类，路径常量置顶。
5. **令牌链路集中**：认证/刷新/登出逻辑只在 `common/services/auth_interceptor.dart`、`modules/authorization/api/auth_service.dart` 与 `modules/authorization/session.dart`；他处禁止手动拼 Authorization 头。
6. **SSE 协议集中**：流式解析只在 `modules/ai/api/ai_service.dart`；后端协议变更只改该文件并同步本目录文档。
7. **状态只用 provider**：ChangeNotifier + watch/read；跨页共享状态进模块的 `providers/`，并在 `app.dart` 的 `MultiProvider` 注册，禁止页面级全局变量。
8. **主题与尺寸**：颜色一律 colorScheme（主题在 `common/theme.dart`）；宽屏限宽交给 `PhoneShell`，页面禁止自建 maxWidth 逻辑。
9. **平台壳三处同步**：桌面窗口尺寸/应用名改动必须 linux/windows/macos 同步；Android/iOS 网络与明文传输配置不得删除。
10. **依赖白名单**：`dio`、`provider`、`shared_preferences`、`flutter_localizations`、`file_picker`（文档上传）；新增需登记理由，禁止引入 UI 组件库/路由库/新状态库。
11. **中文文案**：界面与错误提示全部中文；`flutter analyze` 0 issue（含 info）为完成门槛。

## 3. 典型改动清单

| 改动 | 必做 |
| :--- | :--- |
| 新增页面 | 放所属模块 `modules/<模块>/pages/xxx_page.dart`；挂入口（对话页功能卡片或 Navigator.push）；双主题+宽屏验收 |
| 新增后端能力 | 模块内 `types`（+单测）→ `api` 方法 → `providers` 动作 → `pages` 调用；错误中文化 |
| 新增业务模块 | 建 `modules/<新模块>/{api,types,providers,pages}`（有代码才建目录）；服务注册进 `common/app_core.dart`；provider 注册进 `app.dart` |
| 改登录/注册 | 读 `common/services/auth_interceptor.dart` 与 `modules/authorization/`；回归 401 刷新与登出吊销链路 |
| 改 AI 对话 | 只动 `modules/ai/api/ai_service.dart`、`modules/ai/providers/chat_provider.dart`；本地模式规则改 `common/services/local_assistant.dart`（带单测） |
| 改主题 | `common/theme.dart` 单点修改；亮暗两套同时验收 |
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

提交前至少保证 `flutter analyze` + `flutter test` 通过；分层越界检查（三条均须无输出）：

```bash
grep -rn "package:dio" lib/modules | grep -v "/api/" | grep -v "settings_page.dart"
grep -rn "material.dart" lib/modules/*/providers
grep -rn "modules/.*/pages" lib/common
```
