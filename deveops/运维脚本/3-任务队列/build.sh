#!/usr/bin/env bash
# ==============================================================================
# 一键发布任务队列
#   ./build.sh           构建任务镜像并生成部署目录（不启动）
#   ./build.sh --up      构建完成后立即启动/更新
# 可选环境变量:
#   SKIP_BUILD=1         跳过镜像构建（部署机已 docker load 镜像时用）
# ==============================================================================
source "$(dirname "$0")/../lib.sh"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$KIT_DIR/deploy.env"

require_cmd docker
require_cmd rsync

IMAGE="$(resolve_task_image)"
log "部署目录: $DEPLOY_DIR"
log "任务镜像: $IMAGE (worker ${TASK_REPLICAS}x${TASK_CONCURRENCY}, 队列 $TASK_QUEUES)"

# ---------- 1. 任务镜像 ----------
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    log "[1/3] 构建任务镜像 ..."
    build_backend_image "$IMAGE" "$BACKEND_DIR/tools/docker_task/Dockerfile.task"
else
    log "[1/3] 跳过镜像构建(SKIP_BUILD=1)"
fi

# ---------- 2. 部署目录骨架 ----------
log "[2/3] 初始化部署目录 ..."
mkdir -p "$DEPLOY_DIR/app/log" "$DEPLOY_DIR/app/temp_source"
cp "$KIT_DIR/ctl.sh" "$DEPLOY_DIR/ctl.sh"
cp "$KIT_DIR/docker-compose.yml" "$DEPLOY_DIR/docker-compose.yml"
chmod +x "$DEPLOY_DIR/ctl.sh"

cat > "$DEPLOY_DIR/.env" <<EOF
# 由 3-任务队列/deploy.env 生成；改规模/队列请改源文件后重新执行 build.sh
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME
TASK_IMAGE=$IMAGE
TASK_REPLICAS=$TASK_REPLICAS
TASK_CONCURRENCY=$TASK_CONCURRENCY
TASK_QUEUES=$TASK_QUEUES
TASK_POOL=$TASK_POOL
HOST_PROBE_PORT=$HOST_PROBE_PORT
HOST_PROBE_TOKEN=$HOST_PROBE_TOKEN
EOF

# ---------- 3. 外挂代码/配置 ----------
log "[3/3] 同步外挂代码 ..."
sync_backend "$DEPLOY_DIR/app"

log "完成：任务部署目录 $DEPLOY_DIR"
log "部署机操作: $DEPLOY_DIR/ctl.sh up|status|logs|scale"

if [ "${1:-}" = "--up" ]; then
    log "启动/更新容器 ..."
    "$DEPLOY_DIR/ctl.sh" up
    "$DEPLOY_DIR/ctl.sh" status
fi
