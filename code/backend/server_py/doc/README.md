# 后端文档导航（server_py）

> 本目录只放**后端实现与后端约束**。文档分层归属、跨层主题矩阵与防冗余规则统一见 [文档总索引](../../../../doc/README.md)（唯一事实来源，本文件不重复定义）；部署与跨版本升级在 [deveops/](../../../../deveops/README.md)；AI 协作规则见 [README_AI.md](../README_AI.md)。

## 后端文档

| 文档 | 内容 | 何时读 |
| :--- | :--- | :--- |
| [01-开发指南](dev/01-开发指南.md) | 七类目录、分层职责、新增模块清单、编码约定 | 开发前 |
| [02-目录结构](dev/02-目录结构.md) | `src/` 全量目录说明与模块边界 | 找代码位置 |
| [03-配置与初始化](dev/03-配置与初始化.md) | 配置分层、启动时序、首启建表/种子/管理员、重置与排错 | 新环境启动 / 配置变更 |
| [04-数据库迁移](dev/04-数据库迁移.md) | Alembic 基线、首启 stamp、版本升级、回滚、数据迁移 | 改表 / 版本升级 |
| [05-权限体系与接入](dev/05-权限体系与接入.md) | Casbin 域分离 RBAC、项目数据权限、权限点声明 | 接入权限 |
| [06-权限接入FAQ](dev/06-权限接入FAQ.md) | controller 权限装饰器、菜单/按钮/接口对应关系 | 新增接口 |
| [07-大模型与AI能力](dev/07-大模型与AI能力.md) | 模型配置、LLM/重排/OCR/语音、RAG 调用链 | 接 AI 能力 |
| [08-内存与性能](dev/08-内存与性能.md) | 重库惰性加载、启动内存、向量检索性能 | 性能优化 |
| [09-依赖管理](dev/09-依赖管理.md) | uv、依赖清单、重库约束 | 加依赖 |
| [tag_doc/](tag_doc/version_info.md) | 后端版本记录与待办 | 发版 / 查变更 |
| [sql/](sql/) | 模块建表示例 SQL | 手写 DDL 参考 |

## 后端入口速查

| 能力 | 文件 |
| :--- | :--- |
| 服务入口 + router 注册 | `src/app.py` |
| Celery Worker | `src/app_task.py` |
| 启动生命周期 | `src/common/config/lifespan.py` |
| 运行时装配 | `src/common/runtime.py` |
| 配置加载 | `src/common/config/index.py` |
| 数据库管理器 | `src/common/config/db.py` |
| 动态配置 schema | `src/common/config/dynamic/schemas.py` |
| 迁移入口 | `alembic/env.py`、`alembic/versions/` |
| 权限声明 | `src/module_authorization/config/permissions.py`、`src/module_rag/config/permissions.py` |

## 常用命令

```bash
cd code/backend/server_py
uv sync
python src/app.py                 # 默认 0.0.0.0:6666（config.yaml）
uv run pytest tests -x            # 测试
uv run alembic upgrade head       # 数据库升级
```
