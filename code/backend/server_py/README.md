# server_py — 后端基线库

Python 3.13 + FastAPI + SQLAlchemy 2.0(异步) + SQLModel + PostgreSQL/SQLite + Milvus/LanceDB + Redis/Fakeredis + Celery。

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
# 开发镜像
bash tools/docker_dev/build.sh

# 二进制构建
bash tools/docker_build/linux_build.sh
bash tools/docker_build/build.sh
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
