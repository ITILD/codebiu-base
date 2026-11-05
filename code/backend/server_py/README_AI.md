# server_py — AI 协作规则（后端分层）

> 全局工作流（需求 → 批准 → 开发 → 交付）见根 [README_AI.md](../../../README_AI.md)；前端规则见 [frontend/vue3/README_AI.md](../../frontend/vue3/README_AI.md)；文档导航见 [doc/README.md](doc/README.md)。
> 本文件只约束**后端代码与后端文档**。

## 1. 修改前必读

1. 功能在根 [需求功能登记册](../../../doc/02-设计文档/00-需求功能登记册.md) 为「已批准」（缺陷/文档/纯重构/依赖升级走豁免）。
2. 读 [01-开发指南](doc/dev/01-开发指南.md) 与 [02-目录结构](doc/dev/02-目录结构.md)，确认改动落在哪一层。
3. 涉及配置/建表/升级时，同时读 [03-配置与初始化](doc/dev/03-配置与初始化.md) 与 [04-数据库迁移](doc/dev/04-数据库迁移.md)。
4. 涉及权限时读 [05-权限体系与接入](doc/dev/05-权限体系与接入.md)。

## 2. 硬规则（后端）

1. **Python 3.13 新类型语法**：用 `X | None`、`list[X]`、`dict[K, V]`；禁止 `typing.Optional/Union/List`。
2. **七类目录固定**：`controller / service / dao / do / dependencies / config / utils`。禁止自建 `api/`、`dto/`、`types/`、`core/` 等平行目录。
3. **层间职责固定**：
   - `controller` 只做参数校验、权限装饰器、调度 service；
   - `service` 只写业务逻辑，跨模块调用唯一入口，能力契约 `Protocol` 随实现放这里；
   - `dao` 只碰关系库/向量库；
   - `do` 只放对象（表模型/请求响应体/DTO/枚举/上下文），不含逻辑；
   - `dependencies` 只装配 service/dao 单例；
   - `config` 只放路由挂载、权限声明、模块常量；
   - `utils` 只放无业务状态的纯工具与外部服务适配。
4. **三层同名对应**：`controller / service / dependencies` 一条能力一条线（如 `llm`、`voice`、`ocr`、`rerank`、`model_config`），禁止出现无 controller 的独立能力 service。
5. **跨模块只依赖 service + dependencies**：禁止引用对方 controller/dao/do/utils；依赖方向固定 `module_rag → module_office → module_ai`。
6. **通用能力下沉 `common/`**：跨模块复用的配置、数据库、工具、中间件不再建业务模块。
7. **新模块必须注册**：`src/app.py` import 模块 `config/server.py`；权限点写 `config/permissions.py`，并与前端 `menu.ts` 一致。
8. **配置与密钥**：
   - `config.yaml` 入 git，只放零依赖默认值与 `to set real key` 占位，**严禁真实密钥**；
   - 真实数据库/模型密钥只放 `config.dev.yaml`（gitignored）或 `CODEBIU_*` 环境变量；
   - 业务组首启以 yaml 为种子入库，之后以「系统管理 → 通用配置」为唯一事实来源；
   - 引导配置（`db_rel/server/dir/mineru` 等）始终以 yaml 为准。
9. **建表与迁移**：
   - 全新库首启 `create_all` + 自动 `stamp head`；
   - 结构演进必须写 Alembic 增量脚本，不能只改模型；
   - 启动期不自动 upgrade，生产升级显式执行 `alembic upgrade head`；
   - 矢量表/向量库结构不进 Alembic。
10. **异步优先**：数据库/IO 用 `async`；重库（torch 等）惰性 import；禁止 import 期连接数据库。
11. **中文注释**：解释“为什么”而非“是什么”；公共函数写清输入输出与异常。

## 3. 典型改动清单

| 改动 | 必做 |
| :--- | :--- |
| 新增后端模块 | 复制 `module_template/` → 七类目录；`app.py` 注册；权限声明；必要时加字典种子/初始化钩子 |
| 新增接口 | controller 加路由 + 权限装饰器；service 写业务；必要时 dao/do；补测试 |
| 新增表/字段 | `do` 模型 + Alembic `revision --autogenerate` + 人工审查 + `upgrade head` |
| 新增动态配置 | `common/config/dynamic/schemas.py` 声明 schema + 默认值；首启种子 |
| 新增初始化数据 | `config/server.py` 注册 `@register_init_hook`，必须幂等 |
| 新增外部服务 | 放对应模块 `utils/` 适配器；工厂/注册表可扩展；密钥不进基线 |
| 依赖变更 | 先 grep 复用，再确认无 500MB+ 大库，`pyproject.toml` 同步 |

## 4. 验证命令

```bash
cd code/backend/server_py
uv sync
python -c "import sys; sys.path.insert(0,'src'); import app"   # 导入无报错
uv run pytest tests -x
uv run alembic current && uv run alembic heads                # 迁移状态一致
python src/app.py                                             # 启动后访问 /docs
```

## 5. 后端文档地图

- [doc/README.md](doc/README.md)：后端文档导航
- [01-开发指南](doc/dev/01-开发指南.md) · [02-目录结构](doc/dev/02-目录结构.md)
- [03-配置与初始化](doc/dev/03-配置与初始化.md) · [04-数据库迁移](doc/dev/04-数据库迁移.md)
- [05-权限体系与接入](doc/dev/05-权限体系与接入.md) · [06-权限接入FAQ](doc/dev/06-权限接入FAQ.md)
- [07-大模型与AI能力](doc/dev/07-大模型与AI能力.md)
- [08-内存与性能](doc/dev/08-内存与性能.md) · [09-依赖管理](doc/dev/09-依赖管理.md)
- [tag_doc/version_info.md](doc/tag_doc/version_info.md)：版本记录
