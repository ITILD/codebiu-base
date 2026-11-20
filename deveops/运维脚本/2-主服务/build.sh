#!/usr/bin/env bash
# ==============================================================================
# 一键发布主服务 + 前端
#   ./build.sh           构建镜像/前端并生成部署目录（不启动）
#   ./build.sh --up      构建完成后立即启动/更新容器
# 可选环境变量:
#   SKIP_SERVER=1   跳过镜像构建（只更新前端/代码）
#   SKIP_WEB=1      跳过前端构建（只更新后端）
# ==============================================================================
source "$(dirname "$0")/../lib.sh"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$KIT_DIR/deploy.env"

require_cmd docker
require_cmd rsync

IMAGE="$(resolve_image)"
log "部署目录: $DEPLOY_DIR"
log "后端镜像: $IMAGE (前端端口 $NGINX_PORT / 后端端口 $SERVER_PORT)"

# ---------- 1. 后端镜像 ----------
if [ "${SKIP_SERVER:-0}" != "1" ]; then
    log "[1/4] 构建后端镜像 ..."
    build_backend_image "$IMAGE" "$BACKEND_DIR/tools/docker_dev/Dockerfile.dev"
else
    log "[1/4] 跳过镜像构建(SKIP_SERVER=1)"
fi

# ---------- 2. 部署目录骨架 ----------
log "[2/4] 初始化部署目录 ..."
mkdir -p "$DEPLOY_DIR/nginx/html/index" "$DEPLOY_DIR/nginx/conf/conf.d" \
         "$DEPLOY_DIR/nginx/download" "$DEPLOY_DIR/nginx/logs" \
         "$DEPLOY_DIR/nginx/certs" "$DEPLOY_DIR/nginx/www" \
         "$DEPLOY_DIR/app/log" "$DEPLOY_DIR/app/temp_source"
cp "$KIT_DIR/ctl.sh" "$DEPLOY_DIR/ctl.sh"
cp "$KIT_DIR/docker-compose.yml" "$DEPLOY_DIR/docker-compose.yml"
chmod +x "$DEPLOY_DIR/ctl.sh"

# 按 ENABLE_HTTPS 选择 nginx 模板，并替换 server_name
NGINX_CONF="$KIT_DIR/nginx.conf"
[ "${ENABLE_HTTPS:-0}" = "1" ] && NGINX_CONF="$KIT_DIR/nginx.https.conf"
sed "s/__SERVER_NAME__/${DOMAIN:-_}/g" "$NGINX_CONF" > "$DEPLOY_DIR/nginx/conf/conf.d/default.conf"

cat > "$DEPLOY_DIR/.env" <<EOF
# 由 2-主服务/deploy.env 生成；改端口/镜像请改源文件后重新执行 build.sh
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME
SERVER_IMAGE=$IMAGE
NGINX_PORT=$NGINX_PORT
NGINX_HTTPS_PORT=$NGINX_HTTPS_PORT
SERVER_PORT=$SERVER_PORT
DOMAIN=${DOMAIN:-}
CERT_EMAIL=${CERT_EMAIL:-}
EOF

if [ "${ENABLE_HTTPS:-0}" = "1" ]; then
    [ -n "${DOMAIN:-}" ] || warn "ENABLE_HTTPS=1 但未设置 DOMAIN，无法自动签发证书"
    [ -n "${CERT_EMAIL:-}" ] || warn "未设置 CERT_EMAIL，./ctl.sh cert 将无法签发"
    warn "签发证书：./ctl.sh cert（需 $DOMAIN 已解析到本机且公网 80 可达）"
fi

# ---------- 3. 外挂代码/配置 ----------
log "[3/4] 同步外挂代码 ..."
sync_backend "$DEPLOY_DIR/app"

# ---------- 4. 前端 ----------
if [ "${SKIP_WEB:-0}" != "1" ]; then
    log "[4/4] 构建前端 dist ..."
    build_frontend "$DEPLOY_DIR/nginx/html/index"
else
    log "[4/4] 跳过前端构建(SKIP_WEB=1)"
fi

log "完成：前端 http://localhost:$NGINX_PORT | 后端 http://localhost:$SERVER_PORT"
[ "${ENABLE_HTTPS:-0}" = "1" ] && log "HTTPS: https://${DOMAIN:-<域名>}:$NGINX_HTTPS_PORT"
log "部署机操作: $DEPLOY_DIR/ctl.sh up|status|logs"

if [ "${1:-}" = "--up" ]; then
    log "启动/更新容器 ..."
    "$DEPLOY_DIR/ctl.sh" up
    "$DEPLOY_DIR/ctl.sh" status
fi
