#!/usr/bin/env bash
# ==============================================================================
# 导出 compose 项目用到的所有镜像为 tar(离线部署用)
# 用法:
#   ./export_docker_compose_images.sh [compose目录]   # 默认: 部署目录, 再退回当前目录
#   ./export_docker_compose_images.sh /data/myapp     # 指定含 docker-compose.yml 的目录
#   COMPRESS=1 ./export_docker_compose_images.sh      # 导出为 .tar.gz(体积减半)
# 输出: images_YYYYmmdd_HHMMSS.tar(.gz)
# ==============================================================================
set -euo pipefail

DEVOPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
[ -f "$DEVOPS_DIR/docker_dev/deploy.env" ] && source "$DEVOPS_DIR/docker_dev/deploy.env"

DIR="${1:-${DEPLOY_DIR:-.}}"
if [ ! -f "$DIR/docker-compose.yml" ]; then
    echo "[错误] $DIR 下没有 docker-compose.yml" >&2
    exit 1
fi

cd "$DIR"
OUT="images_$(date +%Y%m%d_%H%M%S).tar"

echo "==> 导出目录: $DIR"
if [ "${COMPRESS:-0}" = "1" ]; then
    docker compose images --format json \
        | sed -n 's/.*"Repository":"\([^"]*\)".*"Tag":"\([^"]*\)".*/\1:\2/p' | sort -u \
        | xargs docker save | gzip > "$OUT.gz"
    echo "==> 完成: $DIR/$OUT.gz"
else
    docker compose images | awk 'FNR > 2 {print $2":"$3}' | sort -u | xargs docker save -o "$OUT"
    echo "==> 完成: $DIR/$OUT"
fi
