#!/usr/bin/env bash
# ==============================================================================
# 后端: 构建镜像 + 初始化部署目录 + 同步外挂代码
# 任何 Ubuntu 电脑可直接运行(路径自动推导, 仅 deploy.env 可调)
#   ./build_docker_server.sh            # 构建镜像 + 同步(不启动)
#   ./build_docker_server.sh --up       # 构建镜像 + 同步 + 启动/更新容器
# 镜像 tag 自动取 pyproject.toml 的 name:version, 同时刷新 :latest
# ==============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cmd docker

DOCKERFILE="$BACKEND_DIR/tools/docker_dev/Dockerfile.dev"
[ -f "$DOCKERFILE" ] || die "未找到 $DOCKERFILE"

IMAGE="$(resolve_server_image)"
log "后端镜像: $IMAGE (来源: pyproject.toml / SERVER_IMAGE=$SERVER_IMAGE)"

# ---------- 1. 构建镜像(上下文 = 后端根目录, pyproject/uv.lock 在此) ----------
log "[1/3] docker build ..."
docker build -f "$DOCKERFILE" -t "$IMAGE" -t "$(echo "$IMAGE" | cut -d: -f1):latest" "$BACKEND_DIR"

# ---------- 2. 初始化部署目录(compose/.env/ctl.sh/nginx/redis 骨架) ----------
log "[2/3] 初始化部署目录: $DEPLOY_DIR"
init_deploy_dir "$IMAGE"

# ---------- 3. 同步外挂代码/配置(镜像只含环境, 代码走 volume) ----------
log "[3/3] 同步外挂代码 ..."
sync_backend_runtime

log "完成。部署目录: $DEPLOY_DIR"

# ---------- 可选: 启动/更新容器 ----------
if [ "${1:-}" = "--up" ]; then
    log "启动/更新容器 ..."
    dc up -d
    dc ps
fi
