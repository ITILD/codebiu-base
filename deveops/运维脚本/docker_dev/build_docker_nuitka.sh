#!/usr/bin/env bash
# ==============================================================================
# 后端(Nuitka 编译版): 源码编译为二进制的镜像, 用于闭源交付
#   ./build_docker_nuitka.sh            # 编译 + 同步外挂(不启动)
#   ./build_docker_nuitka.sh --up       # 编译 + 同步 + 启动
# 镜像 tag: <name>:<version>-nuitka (如 base-server:0.1.0-nuitka), 与 uv 版共存
# 切回 uv 版: 跑 ./build_docker_server.sh 即可(.env 的 SERVER_IMAGE 会刷回)
# 注意: 首次编译 20-60 分钟; 体积通常大于 uv 版(二进制依赖省不掉+编译膨胀)
# ==============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cmd docker

DOCKERFILE="$BACKEND_DIR/tools/docker_build/Dockerfile.dist"
[ -f "$DOCKERFILE" ] || die "未找到 $DOCKERFILE"

BASE="$(resolve_server_image)"
NAME="${BASE%%:*}"
VER="${BASE##*:}"
IMAGE="$NAME:$VER-nuitka"

log "后端镜像(Nuitka): $IMAGE"
log "[1/3] docker build (首次 20-60 分钟, 修改代码重编译有 ccache 加速)..."
docker build -f "$DOCKERFILE" -t "$IMAGE" "$BACKEND_DIR"

log "[2/3] 初始化部署目录: $DEPLOY_DIR"
init_deploy_dir "$IMAGE"   # .env 的 SERVER_IMAGE 切到 nuitka 镜像

log "[3/3] 同步外挂(config/public 运行时仍需要; src 对本镜像无效但无害) ..."
sync_backend_runtime

log "完成。部署目录: $DEPLOY_DIR (镜像内无源码)"

if [ "${1:-}" = "--up" ]; then
    log "启动/更新容器 ..."
    dc up -d
    dc ps
fi
