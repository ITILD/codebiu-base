#!/usr/bin/env bash
# ==============================================================================
# 公共函数库: 被 build_*.sh / update_code.sh source, 不直接执行
# 路径约定(全自动推导, 无绝对路径依赖):
#   本目录 = deveops/运维脚本/docker_dev
#   仓库根 = 本目录上三级 (code/ deveops/ 所在处)
# ==============================================================================
set -euo pipefail

DEVOPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DEVOPS_DIR/../../.." && pwd)"

BACKEND_DIR="$REPO_ROOT/code/backend/server_py"
FRONTEND_DIR="$REPO_ROOT/code/frontend/vue3"
NGINX_CONF_SRC="$DEVOPS_DIR/default.conf"
COMPOSE_TPL_DIR="$DEVOPS_DIR/compose"

# 加载部署配置(同名环境变量优先, deploy.env 内已用 ${VAR:-default} 兜底)
# shellcheck disable=SC1091
source "$DEVOPS_DIR/deploy.env"

log()  { echo -e "\033[32m==>\033[0m $*"; }
warn() { echo -e "\033[33m[警告]\033[0m $*" >&2; }
die()  { echo -e "\033[31m[错误]\033[0m $*" >&2; exit 1; }

# 依赖检查
require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1 (Ubuntu: sudo apt-get install -y $1)"
}

# 从 pyproject.toml [project] 段解析字段(只取第一个匹配, 避开 [[tool.uv.index]] 的 name)
read_pyproject() {  # $1=字段名
    sed -n 's/^'"$1"' *= *"\(.*\)"/\1/p' "$BACKEND_DIR/pyproject.toml" | head -n 1
}

# 后端镜像 tag: 优先 SERVER_IMAGE, 否则 pyproject name:version
resolve_server_image() {
    if [ -n "$SERVER_IMAGE" ]; then
        echo "$SERVER_IMAGE"
        return
    fi
    local name version
    name="$(read_pyproject name)"   || true
    version="$(read_pyproject version)" || true
    [ -n "$name" ]    || die "无法从 $BACKEND_DIR/pyproject.toml 解析出 name"
    [ -n "$version" ] || die "无法从 $BACKEND_DIR/pyproject.toml 解析出 version"
    echo "${name}:${version}"
}

# compose 命令(固定在部署目录执行, 自动读同目录 .env)
dc() {
    require_cmd docker
    (cd "$DEPLOY_DIR" && docker compose --env-file .env "$@")
}

# 由 ENABLE_PG/ENABLE_REDIS 计算 compose profiles(空 = 不启本地中间件)
compose_profiles() {
    local p=""
    [ "$ENABLE_PG" = "1" ] && p="pg"
    [ "$ENABLE_REDIS" = "1" ] && p="${p:+$p,}redis"
    echo "$p"
}

# ---------------------------------------------------------------- 部署目录骨架 --
# 初始化 $DEPLOY_DIR: compose 文件 / .env / ctl.sh / nginx / redis.conf
# 幂等: 已存在的文件不覆盖(仅 .env 中的 SERVER_IMAGE / COMPOSE_PROFILES 每次刷新)
init_deploy_dir() {  # $1=镜像tag
    local image="$1"
    mkdir -p \
        "$DEPLOY_DIR/nginx/html/index" \
        "$DEPLOY_DIR/nginx/conf/conf.d" \
        "$DEPLOY_DIR/nginx/download" \
        "$DEPLOY_DIR/server_py/log" \
        "$DEPLOY_DIR/server_py/temp_source" \
        "$DEPLOY_DIR/postgres/init" \
        "$DEPLOY_DIR/redis/data"

    # 1. compose + 部署侧控制脚本(已存在则跳过, 想重新生成可先删除)
    for f in docker-compose.yml ctl.sh; do
        if [ ! -f "$DEPLOY_DIR/$f" ]; then
            cp "$COMPOSE_TPL_DIR/$f" "$DEPLOY_DIR/$f"
            chmod +x "$DEPLOY_DIR/$f"
        fi
    done

    # 2. .env: 首次生成全量; 之后只刷新 SERVER_IMAGE/COMPOSE_PROFILES 行(密码/端口以手改为准)
    local profiles
    profiles="$(compose_profiles)"
    if [ ! -f "$DEPLOY_DIR/.env" ]; then
        cat > "$DEPLOY_DIR/.env" <<EOF
# 由 deploy.env 生成的运行配置, 可手工修改; SERVER_IMAGE/COMPOSE_PROFILES 会在每次构建时被刷新
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME
SERVER_IMAGE=$image
COMPOSE_PROFILES=$profiles
NGINX_PORT=$NGINX_PORT
SERVER_PORT=$SERVER_PORT
PG_PORT=$PG_PORT
REDIS_PORT=$REDIS_PORT
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EOF
        log "生成 $DEPLOY_DIR/.env (本地中间件: ${profiles:-无, 直连远程})"
    else
        sed -i 's|^SERVER_IMAGE=.*|SERVER_IMAGE='"$image"'|; s|^COMPOSE_PROFILES=.*|COMPOSE_PROFILES='"$profiles"'|' "$DEPLOY_DIR/.env"
    fi

    # 3. nginx 配置
    cp "$NGINX_CONF_SRC" "$DEPLOY_DIR/nginx/conf/conf.d/default.conf"

    # 4. redis 配置(缺失时 docker 挂载会自动建同名目录导致启动失败, 必须预置)
    if [ ! -f "$DEPLOY_DIR/redis/redis.conf" ]; then
        cat > "$DEPLOY_DIR/redis/redis.conf" <<'EOF'
bind 0.0.0.0
protected-mode no
appendonly yes
maxmemory 512mb
maxmemory-policy allkeys-lru
EOF
    fi
}

# ---------------------------------------------------------------- 外挂同步 --
# 把后端"可变内容"同步到部署目录(与 docker-compose.yml 的 volumes 严格一致)
# 镜像内只含 python 环境+依赖; 代码/配置走外挂 => 更新代码无需重建镜像
sync_backend_runtime() {
    local dst="$DEPLOY_DIR/server_py" del_flag=""
    [ "$SYNC_DELETE" = "1" ] && del_flag="--delete"
    mkdir -p "$dst"

    log "同步后端代码 src/ -> $dst/src"
    rsync -a $del_flag "$BACKEND_DIR/src/" "$dst/src/"

    log "同步静态资源 public/ -> $dst/public"
    rsync -a $del_flag "$BACKEND_DIR/public/" "$dst/public/"

    # 配置文件逐个复制(存在才复制: config.yaml 基线 + 任意 config.<env>.yaml 环境层)
    local f
    for f in "$BACKEND_DIR"/config*.yaml "$BACKEND_DIR/rbac_model.conf"; do
        [ -f "$f" ] || continue
        log "同步配置 $(basename "$f")"
        cp "$f" "$dst/"
    done
}
