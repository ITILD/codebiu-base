# deveops 部署运维

部署只分四套，彼此独立、按需组合。每套目标机器上最终只有 **`ctl.sh` + `docker-compose.yml` + `.env`**，新人只需记住 `./ctl.sh up`。

| 套件 | 部署到哪 | 内容 |
| :--- | :--- | :--- |
| [1-依赖环境](./运维脚本/1-依赖环境/) | 依赖主机 | PostgreSQL + Redis + Milvus + RustFS |
| [2-主服务](./运维脚本/2-主服务/) | 业务主机 | nginx + 后端 API + 前端静态页 |
| [3-任务队列](./运维脚本/3-任务队列/) | 任务主机 | Celery worker + beat + 宿主机探针 |
| [4-客户端](./运维脚本/4-客户端/) | 本地打包机 | Android APK / Linux 桌面端 |
| [5-服务器管理](./运维脚本/5-服务器管理/) | 本地（不入库） | 各主机域名/IP/SSH/部署目录清单，供 AI IDE 部署 |

## 最快上手

### ① 依赖环境（只需一次）

```bash
cd deveops/运维脚本/1-依赖环境
./ctl.sh up          # 首次自动生成 .env，按需改密码后重新 up
./ctl.sh status
```

部署到远程主机时，把整个 `1-依赖环境/` 目录拷过去执行同样命令即可。数据在 `data/`，`down` 不会删数据。

文件服务（RustFS）需要 HTTPS 时：在 `.env` 填 `FILE_DOMAIN`（建议用主域名子域名）、`CERT_EMAIL`，执行 `./ctl.sh cert`。之后 `https://FILE_DOMAIN` 即 S3 端点，RustFS 自身端口只监听 `127.0.0.1`；控制台用 SSH 隧道访问。

### ② 主服务 + 前端

```bash
cd deveops/运维脚本/2-主服务
./build.sh --up      # 构建后端镜像 + 前端 dist + 生成部署目录 + 启动
./update.sh          # 以后只改代码：同步 + 重启
```

部署目录默认 `~/a_apps/codebiu-base/server`，可在 [deploy.env](./运维脚本/2-主服务/deploy.env) 修改。拷到服务器后同样只需：

```bash
./ctl.sh up|status|logs|restart
```

**HTTPS（可选，nginx + certbot）**：在 `deploy.env` 设置 `ENABLE_HTTPS=1`、`DOMAIN=app.example.com`、`CERT_EMAIL`，`./build.sh` 生成 [nginx.https.conf](./运维脚本/2-主服务/nginx.https.conf) 后执行 `./ctl.sh cert` 即可签发并启动；之后 certbot 容器自动续期、nginx 自动 reload。手动证书放部署目录 `nginx/certs/{fullchain.pem,privkey.pem}` 同样可用。

### ③ 任务队列

```bash
cd deveops/运维脚本/3-任务队列
./build.sh --up      # 构建独立 task 镜像 + 生成部署目录 + 启动
./update.sh          # 以后只改代码
```

任务机最终同样只有 `ctl.sh + docker-compose.yml + .env`。扩缩容：

```bash
./ctl.sh scale 4     # task_worker 临时调到 4 副本
```

### ④ 客户端

```bash
cd deveops/运维脚本/4-客户端
./build_android.sh   # dist/CodeBiu-<abi>.apk
./build_desktop.sh   # dist/CodeBiu-x86_64.AppImage + tar.gz
```

### ⑤ 服务器管理（远程部署 / 交给 AI IDE）

真实清单放 [servers.yaml](./运维脚本/5-服务器管理/)（已被 Git 忽略），把主服务、任务队列、依赖环境三台机器的域名、IP、SSH 端口、用户、私钥路径、部署目录写进去，AI IDE 就能按清单构建并发布：

```bash
cd deveops/运维脚本/5-服务器管理
cp servers.example.yaml servers.yaml && chmod 600 servers.yaml
# 编辑 servers.yaml，私钥放 keys/ 并 chmod 600
./check.sh           # 逐台验证 SSH 与 docker
```

## 只有两个配置文件需要关心

| 文件 | 作用 |
| :--- | :--- |
| `code/backend/server_py/config.dev.yaml` | 应用连哪个库/Redis/Milvus/S3 |
| 各套件的 `deploy.env` / `.env` | 端口、密码、部署目录、副本数 |

## 单机全量示意（新手最常用）

```bash
# 1) 起依赖（本机 20001/20002/20005/20006）
cd deveops/运维脚本/1-依赖环境 && ./ctl.sh up

# 2) config.dev.yaml 里把 db_rel/redis/milvus 指向 127.0.0.1 对应端口
#    注意：db_rel/server/dir 改 yaml 立即生效；
#          db_cache/db_vector/file_system 首次启动后会落库，之后到「系统管理→通用配置」里改
#    Milvus 默认未开鉴权：db_vector 的 user/password 留空（已落库的实例在通用配置页清空）

# 3) 起主服务与任务队列
cd ../2-主服务 && ./build.sh --up
cd ../3-任务队列 && ./build.sh --up
```

## 离线部署

```bash
# 构建机：导出某个部署目录用到的镜像
deveops/运维脚本/image_manager/export_docker_compose_images.sh ~/a_apps/codebiu-base/server

# 目标机：导入
deveops/运维脚本/image_manager/load_docker_compose_images.sh images_xxx.tar
```

## 其他文档
- [Docker 部署](./部署指南/Docker部署.md)
- [打包构建](./部署指南/打包构建.md)
- [配置与数据库初始化](./运维手册/配置与数据库初始化.md)
- [版本升级与数据库迁移](./运维手册/版本升级与数据库迁移.md)
- [发布流程](./运维手册/发布流程.md)
- [任务与调度运维](./运维手册/任务与调度运维.md)
