#!/usr/bin/env bash
# ==============================================================================
# 部署侧控制脚本(随初始化复制到 $DEPLOY_DIR, 部署机上无需仓库即可使用)
# 用法: ./ctl.sh <命令> [服务名]
#   up        创建并启动全部服务(配置变更后用这个)
#   down      停止并移除容器(数据在宿主机, 不丢)
#   restart   重启服务(默认 server_py; 换了外挂代码/配置后用这个)
#   logs      跟随日志(默认 server_py)
#   status    查看各服务状态
#   reload    热重载 nginx 配置(只改了 nginx conf 时无需重启)
#   ps        同 status
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"   # 定位到部署目录, 与 docker-compose.yml/.env 同级

CMD="${1:-status}"
SVC="${2:-server_py}"

case "$CMD" in
    up)      docker compose --env-file .env up -d ;;
    down)    docker compose --env-file .env down ;;
    restart) docker compose --env-file .env restart "$SVC" ;;
    logs)    docker compose --env-file .env logs -f --tail=200 "$SVC" ;;
    status|ps) docker compose --env-file .env ps ;;
    reload)  docker compose --env-file .env exec nginx nginx -s reload ;;
    *)
        echo "用法: $0 {up|down|restart|logs|status|reload} [服务名: nginx|postgres|redis7|server_py]"
        exit 1
        ;;
esac
