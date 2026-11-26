#!/usr/bin/env bash
# ==============================================================================
# 一键发布（离线镜像包 + 外挂代码）
#   本地构建 → docker save → rsync → 远端 docker load → ctl.sh up
#
#   ./publish.sh deps0        47：PostgreSQL + Redis
#   ./publish.sh main         47：前端 + 后端 API（80/443）
#   ./publish.sh deps1        112：Milvus + RustFS + 文件服务 nginx/certbot
#   ./publish.sh task         112：worker / beat / host_probe
#   ./publish.sh all          按 deps0 → deps1 → main → task 顺序全量发布
#
# 可选参数:
#   --skip-build    跳过本地构建（复用 LOCAL_STAGE，默认 /tmp/codebiu-publish/<role>）
#   --skip-pack     跳过镜像打包（目标机已有镜像，只同步代码/配置）
#   --skip-sync     不同步部署目录
#   --init-config   强制用本地生成的配置覆盖目标机 app/config.dev.yaml
#   --keep-images   目标机 load 后保留镜像包
#   --dry-run       只打印动作，不执行远端命令与镜像打包
#
# 依赖: servers.yaml（cp servers.example.yaml servers.yaml 后填写）
# 配置: 以 code/backend/server_py/config.dev.yaml 为模板，按角色改写数据库/
#       向量库/文件服务地址后随部署目录一起发布（不新增仓库内的密钥文件）
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
SCRIPTS_DIR="$(cd "$HERE/.." && pwd)"
ROOT_DIR="$(cd "$SCRIPTS_DIR/../.." && pwd)"
FILE="$HERE/servers.yaml"
CONFIG_SRC="$ROOT_DIR/code/backend/server_py/config.dev.yaml"

log()  { echo -e "\033[32m==>\033[0m $*"; }
warn() { echo -e "\033[33m[警告]\033[0m $*" >&2; }
die()  { echo -e "\033[31m[错误]\033[0m $*" >&2; exit 1; }

usage() {
    sed -n '2,22p' "$0" | sed -e 's/^# \{0,1\}//'
}

ROLE=""; SKIP_BUILD=0; SKIP_PACK=0; SKIP_SYNC=0; INIT_CONFIG=0; KEEP_IMAGES=0; DRY=0
for arg in "$@"; do
    case "$arg" in
        main|task|deps0|deps1|all) ROLE="$arg" ;;
        --skip-build)  SKIP_BUILD=1 ;;
        --skip-pack)   SKIP_PACK=1 ;;
        --skip-sync)   SKIP_SYNC=1 ;;
        --init-config) INIT_CONFIG=1 ;;
        --keep-images) KEEP_IMAGES=1 ;;
        --dry-run)     DRY=1 ;;
        -h|--help)     usage; exit 0 ;;
        *) die "未知参数: $arg（--help 查看用法）" ;;
    esac
done
[ -n "$ROLE" ] || { usage; exit 1; }
[ -f "$FILE" ] || die "缺少 $FILE：先 cp servers.example.yaml servers.yaml 并填写"
[ "$(stat -c %a "$FILE")" = "600" ] || warn "建议 chmod 600 $FILE（含敏感信息）"
[ -f "$CONFIG_SRC" ] || die "缺少配置模板 $CONFIG_SRC"

# 找一个能 import yaml 的 python
VENV_PY="$ROOT_DIR/code/backend/server_py/.venv/bin/python"
[ -x "$VENV_PY" ] && VENV_PY="$(realpath "$VENV_PY")"
PY=""
for p in "$VENV_PY" python3 python; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c "import yaml" >/dev/null 2>&1; then PY="$p"; break; fi
done
[ -n "$PY" ] || die "需要带 PyYAML 的 python：python3 -m pip install pyyaml"

# 解析 servers.yaml 中某个角色为 KEY=VALUE（供 eval）
role_env() {
    "$PY" - "$FILE" "$1" <<'PYCODE'
import os, shlex, sys, yaml

base = os.path.dirname(os.path.abspath(sys.argv[1]))
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
role = sys.argv[2]
s = data.get(role)
if not isinstance(s, dict):
    sys.exit(f"servers.yaml 中缺少角色: {role}")

ssh = s.get("ssh") or {}
dep = s.get("deploy") or {}
deps = data.get("deps") or {}
cred = deps.get("credentials") or {}
main_ip = (data.get("main") or {}).get("ip") or ""
task_ip = (data.get("task") or {}).get("ip") or ""
file_domain = (data.get("task") or {}).get("file_domain") or ""

def emit(key, value):
    print(f"{key}={shlex.quote(str('' if value is None else value))}")

emit("ROLE_NAME", s.get("name") or role)
emit("REMOTE_IP", s.get("ip") or "")
emit("SSH_HOST", ssh.get("host") or s.get("ip") or "")
emit("SSH_PORT", ssh.get("port") or 22)
emit("SSH_USER", ssh.get("user") or "root")
key = str(ssh.get("key") or "")
if key and not os.path.isabs(key):
    key = os.path.normpath(os.path.join(base, key))
emit("SSH_KEY", key)
emit("REMOTE_DIR", dep.get("dir") or "")
emit("REMOTE_DEPS_DIR", dep.get("deps_dir") or "")
emit("MAIN_IP", main_ip)
emit("TASK_IP", task_ip)
emit("PEER_IP", task_ip if role == "main" else main_ip)
emit("DOMAIN", s.get("domain") or "")
emit("FILE_DOMAIN", file_domain)
emit("CERT_EMAIL", s.get("cert_email") or "")
emit("D_NGINX_PORT", dep.get("nginx_http_port") or 3002)
emit("D_NGINX_HTTPS_PORT", dep.get("nginx_https_port") or 443)
emit("D_ENABLE_HTTPS", 1 if dep.get("enable_https") else 0)
emit("D_SERVER_PORT", dep.get("server_port") or 3001)
emit("D_REPLICAS", dep.get("replicas") or 1)
emit("D_CONCURRENCY", dep.get("concurrency") or 1)
emit("D_QUEUES", dep.get("queues") or "task_queue,q_interactive")
emit("D_PROBE_PORT", dep.get("host_probe_port") or 8700)
emit("D_PROBE_TOKEN", dep.get("host_probe_token") or "change-me")
emit("PG_PASSWORD", cred.get("pg_password") or "change-me")
emit("REDIS_PASSWORD", cred.get("redis_password") or "change-me")
emit("RUSTFS_ACCESS_KEY", cred.get("rustfs_access_key") or "rustfsadmin")
emit("RUSTFS_SECRET_KEY", cred.get("rustfs_secret_key") or "change-me")
emit("MILVUS_PASSWORD", cred.get("milvus_password") or "Milvus@2025root")
PYCODE
}

# 按角色生成部署配置：main 用本机 PG/Redis，task 用 47 公网；向量库与文件服务两台一致
gen_config() {
    local role="$1" stage="$2"
    MAIN_IP="$MAIN_IP" TASK_IP="$TASK_IP" FILE_DOMAIN="$FILE_DOMAIN" \
    PG_PASSWORD="$PG_PASSWORD" REDIS_PASSWORD="$REDIS_PASSWORD" \
    RUSTFS_ACCESS_KEY="$RUSTFS_ACCESS_KEY" RUSTFS_SECRET_KEY="$RUSTFS_SECRET_KEY" \
    MILVUS_PASSWORD="$MILVUS_PASSWORD" \
    "$PY" - "$role" "$CONFIG_SRC" "$stage/app/config.dev.yaml" <<'PYCODE'
import os, re, sys

role, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
main_ip = os.environ["MAIN_IP"]
task_ip = os.environ["TASK_IP"]
fs_domain = os.environ["FILE_DOMAIN"]
pg_pw = os.environ["PG_PASSWORD"]
redis_pw = os.environ["REDIS_PASSWORD"]
ak = os.environ["RUSTFS_ACCESS_KEY"]
sk = os.environ["RUSTFS_SECRET_KEY"]
milvus_pw = os.environ["MILVUS_PASSWORD"]

# 主服务在本机，PG/Redis 通过 host.docker.internal 访问宿主机端口
pg_host = "host.docker.internal" if role == "main" else main_ip
# Milvus 部署在 server_1(112)：主服务(47)经 TASK_IP 访问；任务机本机直连
vector_host = f"http://{task_ip}" if role == "main" else "http://host.docker.internal"
out, sec = [], None
for line in open(src, encoding="utf-8").read().splitlines():
    m = re.match(r"^([a-zA-Z_]+):\s*$", line)
    if m:
        sec = m.group(1)
    if sec == "db_rel":
        if re.match(r"^\s*host:", line): line = f"  host: {pg_host}"
        elif re.match(r"^\s*port:", line): line = "  port: 20001"
        elif re.match(r"^\s*password:", line): line = f'  password: "{pg_pw}"'
    elif sec == "db_cache":
        if re.match(r"^\s*host:", line): line = f"  host: {pg_host}"
        elif re.match(r"^\s*port:", line): line = "  port: 20002"
        elif re.match(r"^\s*password:", line): line = f'  password: "{redis_pw}"'
    elif sec == "tasks":
        if re.match(r"^\s*broker_url:", line): line = f"  broker_url: redis://:{redis_pw}@{pg_host}:20002/3"
        elif re.match(r"^\s*result_backend:", line): line = f"  result_backend: redis://:{redis_pw}@{pg_host}:20002/4"
    elif sec == "db_vector":
        if re.match(r"^\s*host:", line): line = f"  host: {vector_host}"
        elif re.match(r"^\s*port:", line): line = "  port: 20005"
        elif re.match(r"^\s*database:", line): line = "  database: default"
        elif re.match(r"^\s*password:", line): line = f'  password: "{milvus_pw}"'
    out.append(line)

out += [
    "",
    "# ############################# 部署注入: 文件存储 #############################",
    "# 业务组首启入库，之后以 系统管理→通用配置页 为准",
    "file_system:",
    f'  endpoint_url: "https://{fs_domain}"',
    f'  access_key: "{ak}"',
    f'  secret_key: "{sk}"',
    "  bucket: codebiu-base",
    "  region: us-east-1",
    "  secure: true",
]
open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")
PYCODE
    log "  已生成部署配置（$role）: $(basename "$stage")/app/config.dev.yaml"
}

remote_ssh() {
    ssh "${SSH_OPTS[@]}" "$TARGET" "$@"
}

remote_run() {
    if [ "$DRY" = 1 ]; then
        log "[dry-run] ssh $TARGET: $*"
        return 0
    fi
    remote_ssh "$@"
}

# ---------------- 依赖环境（47=server_0 / 112=server_1） ----------------
publish_deps() {
    local n="$1" srole="server_$1" conf_role
    [ "$n" = 0 ] && conf_role=main || conf_role=task
    eval "$(role_env "$conf_role")"
    [ -n "$SSH_HOST" ] || die "未配置 $conf_role.ssh"
    [ -n "$REMOTE_DEPS_DIR" ] || die "未配置 $conf_role.deploy.deps_dir"

    local SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -p "$SSH_PORT")
    [ -n "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")
    local RSYNC_RSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -p $SSH_PORT"
    [ -n "$SSH_KEY" ] && RSYNC_RSH="$RSYNC_RSH -i $SSH_KEY"
    local TARGET="$SSH_USER@$SSH_HOST"

    echo
    log "===== 发布依赖 $srole → $TARGET:$REMOTE_DEPS_DIR ====="
    remote_run "mkdir -p '$REMOTE_DEPS_DIR'"
    if [ "$DRY" = 1 ]; then
        log "[dry-run] rsync 1-依赖环境 → $REMOTE_DEPS_DIR"
    else
        rsync -az --delete -e "$RSYNC_RSH" \
            --exclude 'data/' --exclude 'server_0/.env' --exclude 'server_1/.env' \
            "$SCRIPTS_DIR/1-依赖环境/" "$TARGET:$REMOTE_DEPS_DIR/"
    fi

    local ENV_BODY
    if [ "$n" = 0 ]; then
        ENV_BODY="# server_0 依赖（PostgreSQL + Redis）
COMPOSE_PROJECT_NAME=codebiu-deps-0
COMPOSE_PROFILES=db
PG_PORT=20001
POSTGRES_DB=codebiu_base
POSTGRES_USER=here
POSTGRES_PASSWORD=$PG_PASSWORD
REDIS_PORT=20002
REDIS_PASSWORD=$REDIS_PASSWORD
REDIS_MAXMEMORY=256mb"
    else
        ENV_BODY="# server_1 依赖（RustFS + Milvus + attu + 文件服务 nginx/certbot）
COMPOSE_PROJECT_NAME=codebiu-deps-1
COMPOSE_PROFILES=storage,vector
RUSTFS_PORT=20006
RUSTFS_CONSOLE_PORT=20007
RUSTFS_BIND_IP=0.0.0.0
RUSTFS_ACCESS_KEY=$RUSTFS_ACCESS_KEY
RUSTFS_SECRET_KEY=$RUSTFS_SECRET_KEY
MILVUS_PORT=20005
MILVUS_METRICS_PORT=20008
MILVUS_VERSION=v3.0.6
MILVUS_MQ_TYPE=woodpecker
# Milvus 与 RustFS 同机，走 compose 内网，无需 TLS
MILVUS_S3_ENDPOINT=rustfs:9000
MILVUS_S3_SSL=false
MILVUS_S3_REGION=us-east-1
MILVUS_GOMEMLIMIT=1024MiB
ETCD_GOMEMLIMIT=128MiB
ATTU_PORT=20009
FILE_DOMAIN=$FILE_DOMAIN
CERT_EMAIL=$CERT_EMAIL
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443"
    fi

    if [ "$DRY" = 1 ]; then
        log "[dry-run] 写入 $REMOTE_DEPS_DIR/$srole/.env"
        log "[dry-run] cd $REMOTE_DEPS_DIR && ./ctl.sh --role $srole up"
        return 0
    fi

    printf '%s\n' "$ENV_BODY" | remote_ssh "cat > '$REMOTE_DEPS_DIR/$srole/.env'"
    remote_run "cd '$REMOTE_DEPS_DIR' && ./ctl.sh --role $srole up >/dev/null && ./ctl.sh --role $srole status"

    if [ "$n" = 0 ]; then
        log "  等待 PostgreSQL 就绪 ..."
        remote_run "for i in \$(seq 1 30); do docker exec codebiu-deps-0-postgres pg_isready -U here -d codebiu_base >/dev/null 2>&1 && exit 0; sleep 2; done; echo 'PG 未就绪' >&2; exit 1"
    else
        log "  等待 RustFS 就绪 ..."
        remote_run "for i in \$(seq 1 30); do (echo > /dev/tcp/127.0.0.1/20006) >/dev/null 2>&1 && exit 0; sleep 2; done; echo 'RustFS 未就绪' >&2; exit 1"
        log "  等待 Milvus 就绪（最长 5 分钟）..."
        remote_run "for i in \$(seq 1 100); do (echo > /dev/tcp/127.0.0.1/20005) >/dev/null 2>&1 && exit 0; sleep 3; done; echo 'Milvus 未就绪' >&2; exit 1"
    fi
    log "完成 $srole 依赖"
}

# ---------------- 主服务 / 任务队列 ----------------
publish_role() {
    local role="$1"
    eval "$(role_env "$role")"

    [ -n "$SSH_HOST" ] || die "$role 未配置 ssh.host / ip"
    [ -n "$REMOTE_DIR" ] || die "$role 未配置 deploy.dir"
    if [ -n "$SSH_KEY" ] && [ ! -f "$SSH_KEY" ]; then
        die "SSH 密钥不存在: $SSH_KEY"
    fi

    local STAGE="${LOCAL_STAGE:-$HOME/.cache/codebiu-publish/$role}"
    local SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -p "$SSH_PORT")
    [ -n "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")
    local RSYNC_RSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -p $SSH_PORT"
    [ -n "$SSH_KEY" ] && RSYNC_RSH="$RSYNC_RSH -i $SSH_KEY"
    local TARGET="$SSH_USER@$SSH_HOST"

    echo
    log "===== 发布 $ROLE_NAME（$role）→ $TARGET:$REMOTE_DIR ====="

    # 1. 本地构建
    if [ "$SKIP_BUILD" != "1" ]; then
        log "[1/5] 本地构建 → $STAGE"
        if [ "$role" = "main" ]; then
            DEPLOY_DIR="$STAGE" \
            NGINX_PORT="$D_NGINX_PORT" NGINX_HTTPS_PORT="$D_NGINX_HTTPS_PORT" \
            ENABLE_HTTPS="$D_ENABLE_HTTPS" SERVER_PORT="$D_SERVER_PORT" \
            DOMAIN="$DOMAIN" CERT_EMAIL="$CERT_EMAIL" \
                "$SCRIPTS_DIR/2-主服务/build.sh"
        else
            DEPLOY_DIR="$STAGE" \
            TASK_REPLICAS="$D_REPLICAS" TASK_CONCURRENCY="$D_CONCURRENCY" \
            TASK_QUEUES="$D_QUEUES" HOST_PROBE_PORT="$D_PROBE_PORT" \
            HOST_PROBE_TOKEN="$D_PROBE_TOKEN" FS_DOMAIN="$FILE_DOMAIN" \
            MAIN_IP="$MAIN_IP" \
                "$SCRIPTS_DIR/3-任务队列/build.sh"
        fi
    else
        [ -f "$STAGE/docker-compose.yml" ] || die "--skip-build 但 $STAGE 产物不完整"
        log "[1/5] 跳过本地构建（复用 $STAGE）"
    fi

    # 按角色改写配置（构建后覆盖 stage 里的 config.dev.yaml）
    gen_config "$role" "$STAGE"

    # 2. 打包镜像
    local PKG=""
    if [ "$SKIP_PACK" != "1" ]; then
        log "[2/5] 打包业务镜像"
        local IMG
        if [ "$role" = "main" ]; then
            IMG="$(sed -n 's/^SERVER_IMAGE=//p' "$STAGE/.env" | head -n 1)"
        else
            IMG="$(sed -n 's/^TASK_IMAGE=//p' "$STAGE/.env" | head -n 1)"
        fi
        [ -n "$IMG" ] || die "无法从 $STAGE/.env 读取镜像名"
        local -a IMAGES=("$IMG")
        if [ "$role" = "main" ]; then
            local base
            for base in nginx:alpine certbot/certbot; do
                if docker image inspect "$base" >/dev/null 2>&1; then
                    IMAGES+=("$base")
                else
                    warn "本地无基础镜像 $base，目标机将尝试 docker pull"
                fi
            done
        fi
        PKG="$STAGE/image_$(date +%Y%m%d_%H%M%S).tar"
        log "  镜像: ${IMAGES[*]}"
        if [ "$DRY" = 1 ]; then
            log "[dry-run] docker save -o $(basename "$PKG") ${IMAGES[*]}"
            PKG=""
        else
            docker save -o "$PKG" "${IMAGES[@]}"
            tar -tf "$PKG" >/dev/null || die "镜像包校验失败（tar -tf）: $PKG"
            log "  镜像包: $(du -h "$PKG" | cut -f1)  $(basename "$PKG")"
        fi
    else
        log "[2/5] 跳过镜像打包"
    fi

    # 3. 目标机准备（首次自动推配置）
    log "[3/5] 检查目标机"
    remote_run "mkdir -p '$REMOTE_DIR/app'"
    local NEED_CONFIG=0
    if [ "$DRY" != "1" ]; then
        ssh "${SSH_OPTS[@]}" "$TARGET" "test -f '$REMOTE_DIR/app/config.dev.yaml'" 2>/dev/null || NEED_CONFIG=1
    fi
    if [ "$INIT_CONFIG" = "1" ] || [ "$NEED_CONFIG" = "1" ]; then
        [ "$DRY" = 1 ] || warn "推送 $role 角色配置到目标机 app/（首次部署或 --init-config）"
        if [ "$DRY" = 1 ]; then
            log "[dry-run] rsync app/config*.yaml → $REMOTE_DIR/app/"
        else
            rsync -a -e "$RSYNC_RSH" "$STAGE/app/config.dev.yaml" "$TARGET:$REMOTE_DIR/app/config.dev.yaml"
            [ -f "$STAGE/app/config.yaml" ] && rsync -a -e "$RSYNC_RSH" "$STAGE/app/config.yaml" "$TARGET:$REMOTE_DIR/app/config.yaml"
        fi
    fi

    # 4. 同步部署目录
    if [ "$SKIP_SYNC" != "1" ]; then
        log "[4/5] 同步部署目录 → $REMOTE_DIR"
        local -a EXCLUDES=(
            --exclude 'images_*.tar.gz'
            --exclude 'app/log/'
            --exclude 'app/temp_source/'
            --exclude 'nginx/logs/'
            --exclude 'nginx/certs/'
            --exclude 'nginx/download/'
            --exclude 'nginx/html/index_*'
            --exclude 'app/config.yaml'
            --exclude 'app/config.dev.yaml'
        )
        if [ "$DRY" = 1 ]; then
            log "[dry-run] rsync -az --delete ${EXCLUDES[*]} $STAGE/ $TARGET:$REMOTE_DIR/"
        else
            rsync -az --delete -e "$RSYNC_RSH" "${EXCLUDES[@]}" "$STAGE/" "$TARGET:$REMOTE_DIR/"
        fi
    else
        log "[4/5] 跳过部署目录同步"
    fi

    # 5. 上传镜像并启动
    if [ -n "$PKG" ]; then
        log "[5/5] 上传镜像 → 目标机 docker load"
        local LOAD_IMG
        if [ "$role" = "main" ]; then
            LOAD_IMG="$(sed -n 's/^SERVER_IMAGE=//p' "$STAGE/.env" | head -n 1)"
        else
            LOAD_IMG="$(sed -n 's/^TASK_IMAGE=//p' "$STAGE/.env" | head -n 1)"
        fi
        rsync -az -e "$RSYNC_RSH" "$PKG" "$TARGET:$REMOTE_DIR/"
        local BASE
        BASE="$(basename "$PKG")"
        remote_run "cd '$REMOTE_DIR' && docker load -i '$BASE' && docker image inspect '$LOAD_IMG' >/dev/null"
        [ "$KEEP_IMAGES" = "1" ] || remote_run "rm -f '$REMOTE_DIR/$BASE'"
    else
        log "[5/5] 无镜像包需要上传"
    fi

    remote_run "cd '$REMOTE_DIR' && ./ctl.sh up && ./ctl.sh status"

    # 主服务首次签发 HTTPS 证书（HTTP 入口保留，不强制跳转以外的行为）
    if [ "$role" = "main" ] && [ "$D_ENABLE_HTTPS" = "1" ]; then
        remote_run "cd '$REMOTE_DIR' && { test -f nginx/certs/fullchain.pem || ./ctl.sh cert; }"
    fi

    log "完成 $ROLE_NAME"
    if [ "$role" = "main" ]; then
        log "访问: http://$DOMAIN"
        [ "$D_ENABLE_HTTPS" = "1" ] && log "HTTPS: https://$DOMAIN"
        log "提示: 阿里云安全组需放行 80/443"
    else
        log "探针: http://$SSH_HOST:$D_PROBE_PORT/health"
        log "文件服务: https://$FILE_DOMAIN（需 DNS 解析到 $SSH_HOST，并放行 80/443）"
    fi
}

case "$ROLE" in
    deps0) publish_deps 0 ;;
    deps1) publish_deps 1 ;;
    main)  publish_role main ;;
    task)  publish_role task ;;
    all)   publish_deps 0; publish_deps 1; publish_role main; publish_role task ;;
esac
