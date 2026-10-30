#!/usr/bin/env bash
# ==============================================================================
# 导入镜像 tar(离线部署机用)
# 用法:
#   ./load_docker_compose_images.sh                    # 自动找目录下最新的 images_*.tar(.gz)
#   ./load_docker_compose_images.sh /path/images_xxx.tar.gz
# ==============================================================================
set -euo pipefail

if [ -n "${1:-}" ]; then
    FILE="$1"
else
    FILE="$(ls -t images_*.tar images_*.tar.gz 2>/dev/null | head -n 1 || true)"
    [ -n "$FILE" ] || { echo "[错误] 未找到 images_*.tar(.gz), 请指定文件路径" >&2; exit 1; }
fi
[ -f "$FILE" ] || { echo "[错误] 文件不存在: $FILE" >&2; exit 1; }

echo "==> 导入镜像: $FILE"
case "$FILE" in
    *.gz) gunzip -c "$FILE" | docker load ;;
    *)    docker load -i "$FILE" ;;
esac
echo "==> 当前镜像列表:"
docker images
