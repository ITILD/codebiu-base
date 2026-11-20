#!/usr/bin/env bash
# ==============================================================================
# 依赖环境控制脚本（PostgreSQL + Redis + Milvus + RustFS）
# 用法: ./ctl.sh {up|stop|down|restart|logs|status|cert}
# 说明:
#   up      创建并启动全部依赖（首次会自动生成 .env）
#   cert    用 certbot 为 FILE_DOMAIN 签发证书（之后由 certbot 容器自动续期）
#   stop    停止容器（保留容器与数据）
#   down    停止并移除容器（data/ 数据保留）
#   logs    跟随全部日志；也可 ./ctl.sh logs milvus
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# 首次运行：从模板生成 .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "==> 已生成 .env（默认密码仅用于内网自建，请按需修改后重新执行）"
fi

# 读取 .env（COMPOSE_PROJECT_NAME 用于容器名前缀）
set -a
# shellcheck disable=SC1091
. ./.env
set +a
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$PWD" | tr -cd '[:alnum:]_.-')}"
# 本机角色：47 用 db（PG/Redis），112 用 storage（RustFS/Milvus/nginx）
COMPOSE_PROFILES="${COMPOSE_PROFILES:-db,storage}"
export COMPOSE_PROFILES
# storage 角色才有 nginx/certbot
HAS_STORAGE=0
case ",$COMPOSE_PROFILES," in *,storage,*) HAS_STORAGE=1 ;; esac
# 有域名时启用 certbot 容器（自动续期）
PROFILE_ARG=""
if [ "$HAS_STORAGE" = "1" ] && [ -n "${FILE_DOMAIN:-}" ]; then
    PROFILE_ARG="--profile https"
fi
dc() {
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker compose --env-file .env $PROFILE_ARG "$@"
}

CMD="${1:-status}"
SVC="${2:-}"

die() { echo "[错误] $*" >&2; exit 1; }

# 只有 storage 角色（112）才用 nginx；db 角色（47）不生成任何 nginx 目录
if [ "$HAS_STORAGE" = "1" ]; then
    mkdir -p nginx/certs nginx/www
fi

case "$CMD" in
    up)
        if [ "$HAS_STORAGE" != "1" ]; then
            dc up -d
        elif [ -f nginx/certs/fullchain.pem ] && [ -f nginx/certs/privkey.pem ]; then
            dc up -d
        else
            echo "警告: 尚无证书，先执行 ./ctl.sh cert 签发（本次跳过 nginx）" >&2
            dc up -d --scale nginx=0
        fi
        ;;
    cert)
        [ "$HAS_STORAGE" = "1" ] || die "当前 COMPOSE_PROFILES=$COMPOSE_PROFILES，cert 只在 storage 角色执行"
        [ -n "${FILE_DOMAIN:-}" ] || die "请先在 .env 设置 FILE_DOMAIN（如 fs.example.com）"
        [ -n "${CERT_EMAIL:-}" ] || die "请先在 .env 设置 CERT_EMAIL"
        [ "${NGINX_HTTP_PORT:-80}" = "80" ] || echo "提示: NGINX_HTTP_PORT=$NGINX_HTTP_PORT≠80，Let's Encrypt 校验需要公网 80 转发到该端口" >&2
        echo "==> 暂停 nginx 释放 80 端口 ..."
        dc stop nginx >/dev/null 2>&1 || true
        # 首次签发用 standalone；之后由 certbot 容器用 webroot 自动续期
        docker run --rm -p "${NGINX_HTTP_PORT:-80}:80" -v "$PWD/nginx/certs:/etc/letsencrypt" \
            certbot/certbot certonly --standalone -d "$FILE_DOMAIN" \
            --email "$CERT_EMAIL" --agree-tos --no-eff-email \
            || die "证书签发失败：确认 $FILE_DOMAIN 已解析到本机且公网 80 可达"
        docker run --rm -v "$PWD/nginx/certs:/etc/letsencrypt" --entrypoint sh certbot/certbot -c \
            'cp -L /etc/letsencrypt/live/*/fullchain.pem /etc/letsencrypt/fullchain.pem && cp -L /etc/letsencrypt/live/*/privkey.pem /etc/letsencrypt/privkey.pem'
        dc up -d nginx
        echo "==> 完成：https://$FILE_DOMAIN"
        ;;
    stop)      dc stop ;;
    down)      dc down ;;
    restart)   if [ -n "$SVC" ]; then dc restart "$SVC"; else dc restart; fi ;;
    logs)      if [ -n "$SVC" ]; then dc logs -f --tail=200 "$SVC"; else dc logs -f --tail=200; fi ;;
    status|ps) dc ps ;;
    config)    dc config ;;
    *)
        echo "用法: $0 {up|stop|down|restart|logs|status|cert} [服务名]"
        exit 1
        ;;
esac
