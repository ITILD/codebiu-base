#!/usr/bin/env bash
# ==============================================================================
# 主服务+前端 控制脚本（随 build.sh 复制到部署目录，部署机上无需仓库）
# 用法: ./ctl.sh {up|stop|down|restart|logs|status|reload|cert}
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
# 配了域名才启用 certbot 容器（自动续期）
PROFILE_ARG=""
[ -n "${DOMAIN:-}" ] && PROFILE_ARG="--profile https"
dc() {
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker compose --env-file .env $PROFILE_ARG "$@"
}

CMD="${1:-status}"
SVC="${2:-}"

die() { echo "[错误] $*" >&2; exit 1; }

# HTTPS 配置下若证书缺失，nginx 会反复重启
HTTPS_MODE=0
grep -q 'ssl_certificate' nginx/conf/conf.d/default.conf 2>/dev/null && HTTPS_MODE=1
HAVE_CERT=1
[ -f nginx/certs/fullchain.pem ] && [ -f nginx/certs/privkey.pem ] || HAVE_CERT=0

case "$CMD" in
    up)
        if [ "$HTTPS_MODE" = "1" ] && [ "$HAVE_CERT" = "0" ]; then
            echo "警告: 缺少证书，先执行 ./ctl.sh cert 签发（本次只启动后端）" >&2
            dc up -d server
        else
            dc up -d
        fi
        ;;
    cert)
        [ "$HTTPS_MODE" = "1" ] || die "当前是 HTTP 配置：请先在 server_0/deploy.env 设置 ENABLE_HTTPS=1 并重新 ./build.sh"
        [ -n "${DOMAIN:-}" ] || die "缺少 DOMAIN（.env）"
        [ -n "${CERT_EMAIL:-}" ] || die "缺少 CERT_EMAIL（server_0/deploy.env）"
        mkdir -p nginx/certs nginx/www
        [ "${NGINX_PORT:-80}" = "80" ] || echo "提示: NGINX_PORT=$NGINX_PORT≠80，Let's Encrypt 校验需要公网 80 转发到该端口" >&2
        echo "==> 暂停 nginx 释放 80 端口 ..."
        dc stop nginx >/dev/null 2>&1 || true
        # 首次签发用 standalone；之后由 certbot 容器用 webroot 自动续期
        docker run --rm -p "${NGINX_PORT:-80}:80" -v "$PWD/nginx/certs:/etc/letsencrypt" \
            certbot/certbot certonly --standalone -d "$DOMAIN" \
            --email "$CERT_EMAIL" --agree-tos --no-eff-email \
            || die "证书签发失败：确认 $DOMAIN 已解析到本机且公网 80 可达"
        docker run --rm -v "$PWD/nginx/certs:/etc/letsencrypt" --entrypoint sh certbot/certbot -c \
            'cp -L /etc/letsencrypt/live/*/fullchain.pem /etc/letsencrypt/fullchain.pem && cp -L /etc/letsencrypt/live/*/privkey.pem /etc/letsencrypt/privkey.pem'
        dc up -d
        echo "==> 完成：https://$DOMAIN"
        ;;
    stop)      dc stop ;;
    down)      dc down ;;
    restart)   if [ -n "$SVC" ]; then dc restart "$SVC"; else dc restart; fi ;;
    logs)      if [ -n "$SVC" ]; then dc logs -f --tail=200 "$SVC"; else dc logs -f --tail=200; fi ;;
    status|ps) dc ps ;;
    reload)    dc exec nginx nginx -s reload ;;
    *)
        echo "用法: $0 {up|stop|down|restart|logs|status|reload|cert} [服务名: nginx|server]"
        exit 1
        ;;
esac
