#!/usr/bin/env bash
# ==============================================================================
# 运维脚本公共函数（被 2-主服务 / 3-任务队列 / 4-客户端的脚本 source）
# 目录约定：
#   本文件 = deveops/运维脚本/lib.sh
#   仓库根 = 本文件上两级
# ==============================================================================
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_DIR/../.." && pwd)"

BACKEND_DIR="$REPO_ROOT/code/backend/server_py"
FRONTEND_DIR="$REPO_ROOT/code/frontend/vue3"
FLUTTER_DIR="$REPO_ROOT/code/frontend/flutter"
CLIENT_DIST="$SCRIPTS_DIR/4-客户端/dist"

log()  { echo -e "\033[32m==>\033[0m $*"; }
warn() { echo -e "\033[33m[警告]\033[0m $*" >&2; }
die()  { echo -e "\033[31m[错误]\033[0m $*" >&2; exit 1; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"; }

# 从 pyproject.toml 解析字段（只取第一个匹配）
read_pyproject() {
    sed -n 's/^'"$1"' *= *"\(.*\)"/\1/p' "$BACKEND_DIR/pyproject.toml" | head -n 1
}

# 主服务镜像 tag：SERVER_IMAGE 优先，否则取 pyproject 的 name:version
resolve_image() {
    if [ -n "${SERVER_IMAGE:-}" ]; then
        echo "$SERVER_IMAGE"
        return
    fi
    local name version
    name="$(read_pyproject name)"
    version="$(read_pyproject version)"
    [ -n "$name" ] && [ -n "$version" ] || die "无法从 pyproject.toml 解析 name/version"
    echo "$name:$version"
}

# 任务队列镜像 tag：TASK_IMAGE 优先，否则用 <name>-task:<version>
resolve_task_image() {
    if [ -n "${TASK_IMAGE:-}" ]; then
        echo "$TASK_IMAGE"
        return
    fi
    local base name version
    base="$(resolve_image)"
    name="${base%%:*}"
    version="${base##*:}"
    echo "$name-task:$version"
}

# 构建后端/任务镜像（$1=镜像 tag，$2=Dockerfile）
build_backend_image() {
    docker build -f "$2" -t "$1" -t "$(echo "$1" | cut -d: -f1):latest" "$BACKEND_DIR"
}

# 容器内构建前端 dist 并导出（$1=输出目录；失败时旧产物不受影响）
build_frontend() {
    local out="$1" tmp="$1.new"
    rm -rf "$tmp"
    docker build -f "$FRONTEND_DIR/tools/docker_dev/Dockerfile.dev" --output="$tmp" "$FRONTEND_DIR" \
        || die "前端构建失败，线上旧产物未受影响"
    if [ -d "$out" ] && [ -n "$(ls -A "$out" 2>/dev/null)" ]; then
        mv "$out" "${out}_$(date +%Y%m%d_%H%M%S)"
    else
        rm -rf "$out"
    fi
    mv "$tmp" "$out"
    # BuildKit 导出目录默认 700，nginx worker 需要可读
    chmod -R a+rX "$out"
}

# 同步后端可变内容到部署目录（$1=部署目录下的 app 目录）
sync_backend() {
    local dst="$1" del=""
    [ "${SYNC_DELETE:-1}" = "1" ] && del="--delete"
    mkdir -p "$dst/log" "$dst/temp_source"
    log "同步后端代码/配置 -> $dst"
    rsync -a --exclude '__pycache__/' --exclude '*.pyc' $del "$BACKEND_DIR/src/" "$dst/src/"
    rsync -a --exclude '__pycache__/' --exclude '*.pyc' $del "$BACKEND_DIR/public/" "$dst/public/"
    rsync -a --exclude '__pycache__/' --exclude '*.pyc' $del "$BACKEND_DIR/alembic/" "$dst/alembic/"
    local f
    for f in "$BACKEND_DIR"/config*.yaml "$BACKEND_DIR/rbac_model.conf" "$BACKEND_DIR/alembic.ini"; do
        [ -f "$f" ] || continue
        cp "$f" "$dst/"
    done
}
