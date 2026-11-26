#!/usr/bin/env bash
# ==============================================================================
# 任务队列控制脚本（随 build.sh 复制到部署目录，部署机上无需仓库）
# 用法: ./ctl.sh {up|stop|down|restart|logs|status|scale}
#   up [服务...]          创建并启动（不带服务名=全部）
#   scale <数量>          临时调整 task_worker 副本数
#   logs [服务]           跟随日志
# 服务名: task_worker | task_beat | host_probe
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "缺少 .env：请先在源码侧执行 ./build.sh 生成部署目录"; exit 1; }

# 读取 .env（COMPOSE_PROJECT_NAME 用于容器名前缀）
set -a
# shellcheck disable=SC1091
. ./.env
set +a
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$PWD" | tr -cd '[:alnum:]_.-')}"
# 运行模式: all=单容器合并(worker+beat+probe, 适合 2G 小机器) / split=三容器拆分
export COMPOSE_PROFILES="${TASK_MODE:-all}"
dc() {
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker compose --env-file .env "$@"
}

CMD="${1:-status}"
shift || true

case "$CMD" in
    up)        dc up -d "$@" ;;
    stop)      dc stop ;;
    down)      dc down ;;
    restart)   dc restart "$@" ;;
    logs)      dc logs -f --tail=200 "$@" ;;
    status|ps) dc ps ;;
    scale)
        [ -n "${1:-}" ] || { echo "用法: $0 scale <副本数>"; exit 1; }
        dc up -d --scale "task_worker=$1" --no-recreate task_worker
        dc ps
        ;;
    *)
        echo "用法: $0 {up|stop|down|restart|logs|status|scale} [服务名] [副本数]"
        exit 1
        ;;
esac
