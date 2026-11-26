#!/usr/bin/env bash
# ==============================================================================
# 后端更新（47 主服务）
#   ./update-backend.sh             仅同步代码（依赖未变）：rsync 到外挂目录 + 重启 server
#   ./update-backend.sh --full      依赖变化：重新打镜像并发布（跳过前端构建）
#   ./update-backend.sh --dry-run   只打印动作（默认代码模式）
#
# 说明:
#   - 代码模式走 app/src 外挂挂载，改动立即随容器重启生效，不产生新镜像
#   - --full 复用 publish.sh main（SKIP_WEB=1），完成镜像打包/远端 load/up
#   - 前端变更请用 update-frontend.sh
# 依赖: servers.yaml（main 段）、2-主服务/server_0/deploy.env、本地 Docker
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
SCRIPTS_DIR="$(cd "$HERE/.." && pwd)"
KIT_DIR="$SCRIPTS_DIR/2-主服务"
FILE="$HERE/servers.yaml"
MODE=code
DRY=0
for a in "$@"; do
    case "$a" in
        --full) MODE=full ;;
        --dry-run) DRY=1 ;;
        -h|--help) sed -n '2,14p' "$0" | sed -e 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数: $a"; exit 1 ;;
    esac
done

if [ "$MODE" = "full" ]; then
    log() { echo -e "\033[32m==>\033[0m $*"; }
    [ "$DRY" = 1 ] && { log "[dry-run] SKIP_WEB=1 ./publish.sh main --init-config"; exit 0; }
    [ -f "$FILE" ] || { echo "缺少 $FILE"; exit 1; }
    SKIP_WEB=1 "$HERE/publish.sh" main --init-config
    exit 0
fi

[ -f "$FILE" ] || { echo "缺少 $FILE：先 cp servers.example.yaml servers.yaml 并填写"; exit 1; }
# shellcheck disable=SC1091
source "$SCRIPTS_DIR/lib.sh"
# shellcheck disable=SC1091
source "${DEPLOY_ENV:-$KIT_DIR/server_0/deploy.env}"

VENV_PY="$SCRIPTS_DIR/../code/backend/server_py/.venv/bin/python"
[ -x "$VENV_PY" ] && VENV_PY="$(realpath "$VENV_PY")"
PY=""
for p in "$VENV_PY" python3 python; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c "import yaml" >/dev/null 2>&1; then PY="$p"; break; fi
done
[ -n "$PY" ] || die "需要带 PyYAML 的 python"

eval "$("$PY" - "$FILE" <<'PYCODE'
import os, shlex, sys, yaml
base = os.path.dirname(os.path.abspath(sys.argv[1]))
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
s = data.get("main") or {}
ssh = s.get("ssh") or {}
dep = s.get("deploy") or {}
def emit(k, v): print(f"{k}={shlex.quote(str('' if v is None else v))}")
emit("SSH_HOST", ssh.get("host") or s.get("ip") or "")
emit("SSH_PORT", ssh.get("port") or 22)
emit("SSH_USER", ssh.get("user") or "root")
key = str(ssh.get("key") or "")
if key and not os.path.isabs(key):
    key = os.path.normpath(os.path.join(base, key))
emit("SSH_KEY", key)
emit("REMOTE_DIR", dep.get("dir") or "")
PYCODE
)"

[ -n "$SSH_HOST" ] || die "servers.yaml 缺少 main.ssh/ip"
[ -n "$REMOTE_DIR" ] || die "servers.yaml 缺少 main.deploy.dir"
[ -z "$SSH_KEY" ] || [ -f "$SSH_KEY" ] || die "SSH 密钥不存在: $SSH_KEY"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -p "$SSH_PORT")
[ -n "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")
RSYNC_RSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -p $SSH_PORT"
[ -n "$SSH_KEY" ] && RSYNC_RSH="$RSYNC_RSH -i $SSH_KEY"
TARGET="$SSH_USER@$SSH_HOST"
remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

log "===== 更新后端代码 → $TARGET:$REMOTE_DIR/app ====="
EXCLUDES=(--exclude '__pycache__/' --exclude '*.pyc')

if [ "$DRY" = 1 ]; then
    log "[dry-run] rsync src/ public/ alembic/ → $REMOTE_DIR/app/"
    log "[dry-run] 远端: cd $REMOTE_DIR && ./ctl.sh restart server"
    exit 0
fi

log "[1/2] 同步源码（不触碰 config*.yaml）"
rsync -az --delete -e "$RSYNC_RSH" "${EXCLUDES[@]}" "$BACKEND_DIR/src/" "$TARGET:$REMOTE_DIR/app/src/"
rsync -az --delete -e "$RSYNC_RSH" "${EXCLUDES[@]}" "$BACKEND_DIR/public/" "$TARGET:$REMOTE_DIR/app/public/"
rsync -az --delete -e "$RSYNC_RSH" "${EXCLUDES[@]}" "$BACKEND_DIR/alembic/" "$TARGET:$REMOTE_DIR/app/alembic/"

log "[2/2] 重启 server（外挂代码生效）"
remote "cd '$REMOTE_DIR' && ./ctl.sh restart server && ./ctl.sh status"
log "完成：后端代码已更新（依赖变化请用 --full 重新打镜像）"
