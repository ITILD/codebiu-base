# 5-服务器管理

存放「部署到哪台机器」的清单，供 AI IDE / 人工远程发布使用。**真实清单和私钥都不入 Git。**

## 目录

| 文件 | 是否入库 | 说明 |
| :--- | :--- | :--- |
| `servers.example.yaml` | 是 | 字段模板，复制成 `servers.yaml` 后填真实值 |
| `servers.yaml` | 否 | 真实域名/IP/SSH/部署目录/账号密码 |
| `keys/` | 否 | SSH 私钥（`chmod 600`），仅 `.gitkeep` 入库 |
| `check.sh` | 是 | 读取清单逐台测试 SSH 连通性 |

## 初始化

```bash
cd deveops/运维脚本/5-服务器管理
cp servers.example.yaml servers.yaml
chmod 600 servers.yaml
cp ~/.ssh/id_ed25519 keys/main_server.pem && chmod 600 keys/main_server.pem
./check.sh
```

## 服务器角色

三个套件目录内已按 `server_0` / `server_1` 区分配置：

| 套件 | `server_0`（47 主服务机） | `server_1`（112 任务队列机） |
| :--- | :--- | :--- |
| `1-依赖环境` | `server_0/.env.example`：PostgreSQL + Redis | `server_1/.env.example`：RustFS + Milvus + nginx + certbot |
| `2-主服务` | `server_0/deploy.env`：前端 + API | 不部署 |
| `3-任务队列` | 不部署 | `server_1/deploy.env`：worker / beat / host_probe |

```bash
# 依赖环境按角色启动
cd deveops/运维脚本/1-依赖环境
./ctl.sh --role server_0 up     # 47：PG + Redis
./ctl.sh --role server_1 up     # 112：Milvus + RustFS

# 主服务与任务队列的配置已内置角色路径，无需再选
deveops/运维脚本/2-主服务/build.sh
deveops/运维脚本/3-任务队列/build.sh
```

`SERVER_ROLE=server_0 ./ctl.sh up` 与 `--role` 等价；`DEPLOY_ENV=其他路径 ./build.sh` 可临时指定配置文件。

## 字段

三台机器各一个顶层键，结构一致：

- `domain`：主服务已备案域名（启用 HTTPS 必填）
- `file_domain`：依赖环境文件服务（RustFS S3）HTTPS 域名，建议用主域名子域名
- `cert_email`：Let's Encrypt 通知邮箱（首次签发用）
- `ip`：公网 IP
- `ssh`：`host`（空则用 `ip`）、`port`、`user`、`key`（相对本目录或绝对路径）
- `deploy.dir`：该套件在目标机的部署目录（对应 `server_0`/`server_1` 子目录下 `deploy.env` 的 `DEPLOY_DIR`）
- 其余键为套件参数，与 `server_0`/`server_1` 子目录下 `deploy.env` 同名同义：
  - `main.deploy`：`nginx_http_port` / `nginx_https_port` / `enable_https` / `server_port`
  - `task.deploy`：`replicas` / `concurrency` / `queues` / `host_probe_port` / `host_probe_token`
  - `deps.services`：各依赖的宿主端口；`deps.credentials`：与 `1-依赖环境/server_0|server_1/.env` 一致

## 一键发布（publish.sh，离线镜像包）

本机构建镜像与部署目录，打成镜像包后 rsync 到目标机 `docker load` 并启动，不依赖镜像仓库。

```bash
cd deveops/运维脚本/5-服务器管理
cp servers.example.yaml servers.yaml && chmod 600 servers.yaml   # 填 IP/端口/用户/密钥/部署目录
./check.sh                                                      # 先确认两台机 SSH 与 docker 可用

./publish.sh main        # 发布主服务（前端 + 后端）到 main 机器
./publish.sh task        # 发布任务队列到 task 机器
./publish.sh all         # 依次发布
./publish.sh main --dry-run   # 只打印动作，不执行远端与打包（首次排查用）
```

| 参数 | 说明 |
| :--- | :--- |
| `--skip-build` | 跳过本地构建，复用 `LOCAL_STAGE`（默认 `/tmp/codebiu-publish/<role>`）已有产物 |
| `--skip-pack` | 不打包镜像，目标机已有同名镜像时只同步代码/前端并重启 |
| `--skip-sync` | 不同步部署目录，只传镜像并重启 |
| `--init-config` | 首次发布专用：推送本地 `app/config*.yaml`（先改成服务器实际依赖地址） |
| `--keep-images` | 目标机 `docker load` 后保留镜像包 |
| `--dry-run` | 只打印 ssh/rsync/docker save 动作 |

脚本行为要点：
- 同步部署目录时使用 `--delete`，但**保留**远端 `app/config.yaml`、`app/config.dev.yaml`、`nginx/certs/`、`nginx/logs/`、`nginx/download/`、`app/log/`、`app/temp_source/` 以及历史前端目录 `nginx/html/index_*`。
- 镜像从各套件 `.env` 的 `SERVER_IMAGE` / `TASK_IMAGE` 读取，主服务会附带本地已有的 `nginx:alpine`、`certbot/certbot` 基础镜像。
- 首次发布若远端缺 `app/config.dev.yaml`，脚本会提示；需加 `--init-config` 或手动放好指向依赖库（内网 IP/端口）的配置。

## 发布流程（AI IDE 按此执行）

```bash
# ① 依赖环境：首次把目录拷过去起容器（排除本地数据目录；.env 由 ctl.sh 首次生成或单独传）
rsync -az --exclude 'data/' -e "ssh -p <port> -i <key>" \
  deveops/运维脚本/1-依赖环境/ <user>@<deps.ip>:<deps.deploy.dir>/
#  在远端 server_1/.env 填 FILE_DOMAIN/CERT_EMAIL 后先签发文件服务证书，再启动
ssh -p <port> -i <key> <user>@<deps.ip> "cd <deps.deploy.dir> && ./ctl.sh --role server_1 cert"

# ② 主服务：本地构建（镜像+前端+部署目录），再同步 + 启动
#    源目录 = 2-主服务/server_0/deploy.env 的 DEPLOY_DIR（默认 /home/hrzn/D/a_apps/server_0/server）
deveops/运维脚本/2-主服务/build.sh
rsync -az --delete -e "ssh -p <port> -i <key>" \
  /home/hrzn/D/a_apps/codebiu-base/server/ <user>@<main.ip>:<main.deploy.dir>/
#  main.deploy.enable_https=true 时同样先签发证书
ssh -p <port> -i <key> <user>@<main.ip> "cd <main.deploy.dir> && ./ctl.sh cert"

# ③ 任务队列：内部服务，不要暴露公网（默认不配 nginx）
deveops/运维脚本/3-任务队列/build.sh
rsync -az --delete -e "ssh -p <port> -i <key>" \
  /home/hrzn/D/a_apps/server_1/task/ <user>@<task.ip>:<task.deploy.dir>/
ssh -p <port> -i <key> <user>@<task.ip> "<task.deploy.dir>/ctl.sh up"
```

只改业务代码、没改依赖时用各套件的 `update.sh` 代替 `build.sh`，再同步 `app/` 目录即可。

依赖起好后，主服务 `config.dev.yaml`（或「系统管理→通用配置」）里的 PostgreSQL / Redis / Milvus 指向 `deps.ip` 与端口，`file_system.endpoint_url` 用 `https://<deps.file_domain>`（不再直连 20006）。

> 远程机器需能拉取构建机上已构建好的镜像。镜像不在仓库里：先 `docker save` / `image_manager` 导出，到目标机 `docker load`。

## 安全

- `servers.yaml`、`keys/*`、`known_hosts` 已在本目录 `.gitignore` 和仓库根 `.gitignore` 双重排除。
- 建议为部署单独建 SSH 密钥，只授部署所需目录权限，用完可吊销。
- 该清单等价于服务器密码本，不要贴到聊天、工单或截图里。
