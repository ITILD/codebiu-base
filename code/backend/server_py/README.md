# server_py — 后端基线库

Python 3.13 + FastAPI + SQLAlchemy 2.0(异步) + SQLModel + PostgreSQL + Milvus + Redis + Celery + S3 兼容对象存储(rustfs/MinIO)。

> **AI 能力平台落点**：`module_ai` 提供 Model 供给（ai_model + static_func），`module_agent` 提供 SkillRuntime 与 Agent 编排；三层契约见 [04-AI能力平台架构设计](../../../doc/02-设计文档/04-AI能力平台架构设计.md) 与 [05-对话智能体与执行协议设计](../../../doc/02-设计文档/05-对话智能体与执行协议设计.md)。

## 快速开始

```bash
cd code/backend/server_py
uv sync

# 默认配置（config.yaml 会加载 config.dev.yaml）
#   真实 PostgreSQL/Redis/模型：新建 config.dev.yaml 写覆盖项
#   只跑零依赖基线：把 config.yaml 的 config.local_file 置空
python src/app.py            # http://127.0.0.1:6666/docs

# 或指定模块启动
PYTHONPATH=src uv run uvicorn app:app --host 0.0.0.0 --port 6666
```

默认管理员：`admin / admin123`（`config.yaml` 的 `admin` 段）。

## 测试

```bash
uv run pytest tests -x
```

VS Code `settings.json`：

```json
{
  "python.testing.pytestArgs": ["-v", "-s", "--log-cli-level=INFO"]
}
```

## 构建与部署

```bash
# 在仓库根目录执行
deveops/运维脚本/2-主服务/build.sh --up    # 主服务 + 前端
deveops/运维脚本/3-任务队列/build.sh --up  # 任务队列

# Nuitka 闭源交付镜像（可选，本地执行）
python tools/docker_build/build.py
```

部署、配置初始化与版本升级见 [deveops](../../../deveops/README.md)。

## 基础分层

`controller → service → dao → 数据库`；`dependencies` 依赖注入，`do` 承载对象。职责表与链路图见 [01-开发指南](./doc/dev/01-开发指南.md)。

## 项目文档

- [后端文档导航](./doc/README.md)
- [AI 协作规则](./README_AI.md)
- [开发指南](./doc/dev/01-开发指南.md)
- [配置与初始化](./doc/dev/03-配置与初始化.md)
- [数据库迁移](./doc/dev/04-数据库迁移.md)
- [版本信息](./doc/tag_doc/version_info.md)
- [依赖库](./doc/dev/09-依赖管理.md)
- [项目目录](./doc/dev/02-目录结构.md)
