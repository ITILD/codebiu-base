#!/usr/bin/env bash
# ==============================================================================
# 前端: 容器内构建 dist 并导出到部署目录 nginx/html/index(不产出镜像)
#   ./build_dist_web.sh          # 构建前端 dist + 更新 nginx 配置
#   SKIP_RELOAD=1 ./build_dist_web.sh   # 容器未启动时跳过 nginx 热重载
# 需要 BuildKit(Docker 23+ 默认开启)
# ==============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cmd docker

DOCKERFILE="$FRONTEND_DIR/tools/docker_dev/Dockerfile.dev"
[ -f "$DOCKERFILE" ] || die "未找到 $DOCKERFILE"

NGINX_CONTAINER="${COMPOSE_PROJECT_NAME}-nginx"
HTML_DIR="$DEPLOY_DIR/nginx/html/index"

log "[1/3] 初始化部署目录: $DEPLOY_DIR"
init_deploy_dir "$(resolve_server_image)"

# ---------- 构建到临时目录: 成功才替换, 失败保留线上旧 dist ----------
TMP_OUT="$DEPLOY_DIR/nginx/html/.index_new"
rm -rf "$TMP_OUT"
log "[2/3] 容器内构建前端 dist (先出临时目录, 成功后替换) ..."
docker build -f "$DOCKERFILE" --output="$TMP_OUT" "$FRONTEND_DIR" || die "前端构建失败, 线上旧 dist 未受影响: $HTML_DIR"

# ---------- 备份模式: 旧 index 改名; 覆盖模式: 直接替换 ----------
if [ "$DIST_MODE" = "备份" ] && [ -d "$HTML_DIR" ] && [ -n "$(ls -A "$HTML_DIR" 2>/dev/null)" ]; then
    BACKUP_DIR="${HTML_DIR%/}_$(date +%Y%m%d_%H%M%S)"
    log "备份旧 dist: $HTML_DIR -> $BACKUP_DIR"
    mv "$HTML_DIR" "$BACKUP_DIR"
else
    rm -rf "$HTML_DIR"
fi
mv "$TMP_OUT" "$HTML_DIR"
# BuildKit --output 导出的根目录权限为 700, nginx worker 无权进入(403), 统一放开
chmod -R a+rX "$HTML_DIR"
log "前端构建完成: $HTML_DIR"

# ---------- nginx 配置热重载(容器在跑才执行) ----------
log "[3/3] 更新 nginx 配置(default.conf 已在 init 时复制)"
if [ "${SKIP_RELOAD:-0}" != "1" ] && docker ps --format '{{.Names}}' | grep -qx "$NGINX_CONTAINER"; then
    docker exec "$NGINX_CONTAINER" nginx -s reload
    log "nginx 配置热重载完成: $NGINX_CONTAINER"
else
    warn "跳过 nginx 热重载(容器 $NGINX_CONTAINER 未运行或 SKIP_RELOAD=1)"
fi
