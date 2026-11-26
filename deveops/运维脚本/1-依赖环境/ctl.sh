#!/usr/bin/env bash
# ==============================================================================
# 依赖环境控制脚本（PostgreSQL + Redis + Milvus + RustFS）
# 按服务器角色加载配置，数据统一落在本目录 data/：
#   server_0（47 主服务机）  ：PostgreSQL + Redis
#   server_1（112 任务队列机）：RustFS + Milvus + nginx + certbot
#
# 用法:
#   ./ctl.sh --role server_0 up      启动本机角色依赖（首次自动从 .env.example 生成 .env）
#   SERVER_ROLE=server_1 ./ctl.sh up 同上（环境变量方式）
#   ./ctl.sh --role server_1 cert    为 FILE_DOMAIN 签发文件服务证书
#   ./ctl.sh --role server_0 {stop|down|restart|logs|status}
# 说明:
#   stop    停止容器（保留容器与数据）
#   down    停止并移除容器（data/ 数据保留）
#   logs    跟随全部日志；也可 ./ctl.sh --role server_0 logs postgres
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# ---------- 解析 --role（也可用 SERVER_ROLE 环境变量） ----------
ROLE="${SERVER_ROLE:-}"
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --role)   ROLE="${2:-}"; shift 2 || shift ;;
        --role=*) ROLE="${1#*=}"; shift ;;
        *)        ARGS+=("$1"); shift ;;
    esac
done
if [ ${#ARGS[@]} -gt 0 ]; then set -- "${ARGS[@]}"; else set --; fi

# 未指定时按已生成的 .env 自动识别；出现多个角色配置时必须显式指定，避免误启动另一角色
if [ -z "$ROLE" ]; then
    FOUND=()
    for r in server_0 server_1; do
        [ -f "$r/.env" ] && FOUND+=("$r")
    done
    case "${#FOUND[@]}" in
        1) ROLE="${FOUND[0]}" ;;
        0) ROLE="" ;;
        *) echo "[错误] 检测到多个角色 .env（${FOUND[*]}），请用 --role 指定本机角色" >&2; exit 1 ;;
    esac
fi
case "$ROLE" in
    server_0|server_1) ;;
    "") echo "[错误] 请指定服务器角色：./ctl.sh --role server_0 up（或 SERVER_ROLE=server_1 ./ctl.sh up）" >&2; exit 1 ;;
    *)  echo "[错误] 未知角色: $ROLE（可选 server_0 / server_1）" >&2; exit 1 ;;
esac

ROLE_DIR="$PWD/$ROLE"
[ -d "$ROLE_DIR" ] || { echo "[错误] 缺少角色目录: $ROLE_DIR" >&2; exit 1; }
ENV_FILE="$ROLE_DIR/.env"

# 首次运行：从该角色模板生成 .env
if [ ! -f "$ENV_FILE" ]; then
    cp "$ROLE_DIR/.env.example" "$ENV_FILE"
    echo "==> 已生成 $ROLE/.env（默认密码仅用于内网自建，请按需修改后重新执行）"
fi

# 读取 .env（COMPOSE_PROJECT_NAME 用于容器名前缀）
set -a
# shellcheck disable=SC1091
. "$ENV_FILE"
set +a
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-codebiu-deps-${ROLE#server_}}"

# 本机角色决定启动哪一组服务（server_0=db / server_1=storage）
COMPOSE_PROFILES="${COMPOSE_PROFILES:-}"
if [ -z "$COMPOSE_PROFILES" ]; then
    case "$ROLE" in
        server_0) COMPOSE_PROFILES=db ;;
        server_1) COMPOSE_PROFILES=storage ;;
    esac
fi
export COMPOSE_PROFILES
HAS_STORAGE=0
case ",$COMPOSE_PROFILES," in *,storage,*) HAS_STORAGE=1 ;; esac
# 显式逐项传 --profile：CLI 的 --profile 会覆盖 COMPOSE_PROFILES，只传 https 会导致 storage 被禁用
PROFILE_ARGS=()
IFS=',' read -ra _PROFILES <<< "$COMPOSE_PROFILES"
for _p in "${_PROFILES[@]}"; do
    [ -n "$_p" ] && PROFILE_ARGS+=(--profile "$_p")
done
# 有域名时启用 certbot 容器（自动续期）
if [ "$HAS_STORAGE" = "1" ] && [ -n "${FILE_DOMAIN:-}" ]; then
    PROFILE_ARGS+=(--profile https)
fi
dc() {
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" docker compose --env-file "$ENV_FILE" "${PROFILE_ARGS[@]}" "$@"
}

CMD="${1:-status}"
SVC="${2:-}"

die() { echo "[错误] $*" >&2; exit 1; }

# 只有 storage 角色（server_1）才用 nginx；db 角色（server_0）不生成任何 nginx 目录
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
            echo "警告: 尚无证书，先执行 ./ctl.sh --role $ROLE cert 签发（本次跳过 nginx）" >&2
            dc up -d --scale nginx=0
        fi
        ;;
    cert)
        [ "$HAS_STORAGE" = "1" ] || die "当前角色 $ROLE（COMPOSE_PROFILES=$COMPOSE_PROFILES），cert 只在 server_1 执行"
        [ -n "${FILE_DOMAIN:-}" ] || die "请先在 $ROLE/.env 设置 FILE_DOMAIN（如 fs.example.com）"
        [ -n "${CERT_EMAIL:-}" ] || die "请先在 $ROLE/.env 设置 CERT_EMAIL"
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
        echo "用法: $0 --role server_0|server_1 {up|stop|down|restart|logs|status|cert} [服务名]"
        exit 1
        ;;
esac
