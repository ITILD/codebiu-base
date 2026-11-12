# deveops 部署运维文档

运维与自行部署人员的部署运维知识库。

> 本目录只放**服务器环境、部署编排、构建发布、初始化与升级回滚**。业务功能设计、单端代码规范、需求台账在 [项目文档总索引](../doc/README.md)（文档范围与防冗余规则的唯一事实来源）；本地开发环境搭装在 [doc/01-入门/3-开发环境](../doc/01-入门/3-开发环境.md)。

## 目录导航
| 文档 | 内容 |
| :--- | :--- |
| [环境准备](./部署指南/环境准备.md) | 服务器基础环境( Docker / PostgreSQL / Nginx ) |
| [Docker 部署](./部署指南/Docker部署.md) | docker compose 一键部署前后端全家桶 |
| [打包构建](./部署指南/打包构建.md) | 后端镜像构建 / 前端构建 |
| [配置与数据库初始化](./运维手册/配置与数据库初始化.md) | 首次部署：配置分层、建库、首启建表/种子/管理员、验证与重置 |
| [版本升级与数据库迁移](./运维手册/版本升级与数据库迁移.md) | 跨版本升级：Alembic 升级、数据兼容、回滚、向量库/存储变更 |
| [数据库运维](./运维手册/数据库运维.md) | 备份恢复、迁移、向量库扩展 |
| [发布流程](./运维手册/发布流程.md) | 版本发布与回滚步骤 |
| [任务与调度运维](./运维手册/任务与调度运维.md) | Celery worker 与异步任务队列的运行、排障与扩缩容 |

## 架构总览
```mermaid
graph TD
    U[用户浏览器] -->|80/443| N[nginx]
    N -->|静态文件| FE[前端 dist(html)]
    N -->|/base_server 反代| S[server_py 容器]
    S -->|SQL| DB[(postgres 17)]
    S -.->|可选缓存| R[(redis 7)]
    S -->|文件存储| FS[本地挂载 / S3]
```

## 快速开始(最小部署)
```bash
# 1. 准备 docker 环境
docker --version && docker compose version

# 2. 进入部署编排目录
cd deveops/运维脚本/docker_dev/compose

# 3. 按需修改 deploy.env 中的密码/库名/端口

# 4. 启动全部服务(可选 profile: --profile pg / --profile redis)
bash ctl.sh up       # 等价 docker compose --env-file .env up -d

# 5. 查看状态
bash ctl.sh status
```

## 相关资源
- 后端工具脚本：`code/backend/server_py/tools/`
- 后端版本记录：[code/backend/server_py/doc/tag_doc/](../code/backend/server_py/doc/tag_doc/version_info.md)
- 前端版本记录：[code/frontend/vue3/doc/tag_doc/](../code/frontend/vue3/doc/tag_doc/version_info.md)
- 项目总文档：[doc/README.md](../doc/README.md)
- 后端文档：[code/backend/server_py/doc/README.md](../code/backend/server_py/doc/README.md)
- 前端文档：[code/frontend/vue3/doc/README.md](../code/frontend/vue3/doc/README.md)
