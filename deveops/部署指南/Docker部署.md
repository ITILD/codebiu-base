# Docker 部署

四套独立编排，全部由 `deveops/运维脚本/` 下的 `ctl.sh` 控制。每套落到目标机器后只保留：

```
ctl.sh  docker-compose.yml  .env
```

## 1. 依赖环境（`1-依赖环境`）

| 服务 | 镜像 | 默认宿主端口 | 用途 |
| :--- | :--- | :--- | :--- |
| postgres | postgres:17 | 20001 | 业务库 |
| redis | redis:7.2.4 | 20002 | 缓存 + Celery broker |
| milvus | milvusdb/milvus:v3.0.4 | 20005 | 向量库（内置 etcd；对象存储复用 RustFS） |
| rustfs | rustfs/rustfs:latest | 127.0.0.1:20006 / 20007 | S3 对象存储 / 控制台（仅本机） |
| nginx | nginx:alpine | 80 / 443 | 文件服务 HTTPS 入口，反代 RustFS |
| certbot | certbot/certbot | - | 签发与自动续期证书 |

```bash
cd deveops/运维脚本/1-依赖环境
./ctl.sh --role server_0 up   # 47：首次自动生成 server_0/.env（PG + Redis）
./ctl.sh --role server_1 up   # 112：首次自动生成 server_1/.env（Milvus + RustFS）
./ctl.sh --role server_0 status
./ctl.sh --role server_1 logs milvus
```

数据目录在 `data/`，`./ctl.sh down` 只删容器，不删数据。

### 文件服务 HTTPS

```bash
# server_1/.env
FILE_DOMAIN=fs.example.com      # 解析到本机；建议用已备案主域名的子域名
CERT_EMAIL=you@example.com
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

./ctl.sh --role server_1 cert   # certbot standalone 首次签发，随后启动 nginx
```

`./ctl.sh --role server_1 cert` 之后，certbot 容器用 webroot 每 12h 检查续期，nginx 每 12h reload 一次自动加载新证书。
控制台不对公网开放，需要时用 SSH 隧道：`ssh -L 20007:127.0.0.1:20007 user@deps-host`，再访问 `http://127.0.0.1:20007`。

签发后把后端 `file_system.endpoint_url` 改为 `https://fs.example.com`（已初始化过的实例在「系统管理→通用配置」改）。
签名按 Host 计算，nginx 已透传 Host，预签名上传/下载可直接使用。

> Milvus 默认未开启鉴权。首次部署时 `config.dev.yaml` 的 `db_vector.user/password` 留空即可；
> 若库已初始化过，`db_cache/db_vector/file_system` 已落库，需到「系统管理→通用配置」页清空，改 yaml 不再生效。

## 2. 主服务（`2-主服务`）

| 服务 | 用途 | 默认宿主端口 |
| :--- | :--- | :--- |
| nginx | 前端静态页 + `/base_server` 反代 | 3002（HTTP）/ 443（HTTPS） |
| server | 后端 API（容器内 6666） | 3001 |

```bash
cd deveops/运维脚本/2-主服务
./build.sh --up      # 构建 + 生成部署目录 + 启动
./update.sh          # 日常改代码（不重建镜像）
```

部署目录结构（`$DEPLOY_DIR`，默认 `~/a_apps/server_0/server`，配置见 `server_0/deploy.env`）：

```
server/
├── ctl.sh  docker-compose.yml  .env
├── nginx/html/index/        # 前端 dist
├── nginx/conf/conf.d/       # default.conf（HTTP 或 HTTPS，由 build.sh 选择）
├── nginx/certs/             # fullchain.pem / privkey.pem（HTTPS 时）
├── nginx/www/               # ACME 校验目录（certbot webroot）
└── app/                     # src / config / log / temp_source
```

### 启用 HTTPS

```bash
# server_0/deploy.env
ENABLE_HTTPS=1
DOMAIN=app.example.com
CERT_EMAIL=you@example.com
NGINX_PORT=80          # 必须让公网 80 直达本机，否则无法签发
NGINX_HTTPS_PORT=443
```

```bash
./build.sh             # 生成部署目录（选 nginx.https.conf）
./ctl.sh cert          # certbot 签发 + 复制证书 + 启动 nginx
```

- 首次签发用 `certbot standalone`（会短暂停 nginx 占用 80）；之后 certbot 容器用 webroot 每 12h 自动续期，nginx 每 12h `reload` 自动加载新证书。
- 不用 certbot 时，把证书放到 `$DEPLOY_DIR/nginx/certs/{fullchain.pem,privkey.pem}` 再 `./ctl.sh up` 也一样。
- `ctl.sh up` 在 HTTPS 配置下若发现证书缺失，只启动后端并提示先执行 `./ctl.sh cert`，避免 nginx 反复重启。


## 3. 任务队列（`3-任务队列`）

| 服务 | 用途 | 说明 |
| :--- | :--- | :--- |
| task_worker | 消费 `task_queue,q_interactive` | 副本数由 `TASK_REPLICAS` 控制 |
| task_beat | 周期调度触发 | 全局单实例 |
| host_probe | 主服务远程伸缩 worker | 需与主服务登记同一 token |

```bash
cd deveops/运维脚本/3-任务队列
./build.sh --up
./update.sh
./ctl.sh scale 4     # 临时扩到 4 个 worker
```

任务机部署目录结构与主服务一致，只是没有 `nginx/` 和前端产物。

## 4. 常用命令

```bash
./ctl.sh up          # 创建/更新并启动
./ctl.sh stop        # 停止（保留容器）
./ctl.sh down        # 停止并移除容器（数据保留）
./ctl.sh restart     # 重启
./ctl.sh logs        # 跟随日志
./ctl.sh status      # 查看状态
```

## 5. 常见问题

| 现象 | 处理 |
| :--- | :--- |
| 主服务连不上依赖 | 检查 `config.dev.yaml` 的 host/port；远程依赖需放行端口 |
| 上传大文件 413 | 调大 `2-主服务/nginx.conf` 的 `client_max_body_size` 与后端 `file_system.max_size` |
| AI 对话不流式 | nginx 的 `/base_server/` 必须保持 `proxy_buffering off` |
| 改了代码不生效 | 主服务用 `update.sh`；任务队列用 `update.sh`（都会重启进程） |
| 任务不执行 | 确认任务机 `ctl.sh status` 中 worker 正常，且 `config.dev.yaml` 的 Redis 配置一致 |

## 相关
- [服务器管理（远程发布清单）](../运维脚本/5-服务器管理/README.md)
- [打包构建](./打包构建.md)
- [配置与数据库初始化](../运维手册/配置与数据库初始化.md)
- [版本升级与数据库迁移](../运维手册/版本升级与数据库迁移.md)
