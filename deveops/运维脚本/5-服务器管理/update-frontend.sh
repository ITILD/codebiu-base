#!/usr/bin/env bash
# ==============================================================================
# 仅更新 47 主服务前端（不重建后端镜像、不改后端代码）
#   ./update-frontend.sh            构建前端 → 上传 → 原子切换目录（立即生效）
#   ./update-frontend.sh --dry-run  只打印动作
#
# 依赖: servers.yaml（main 段）、2-主服务/server_0/deploy.env、本地 Docker
# 产物暂存: LOCAL_STAGE 可覆盖，默认 ~/.cache/codebiu-update/web
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
SCRIPTS_DIR="$(cd "$HERE/.." && pwd)"
KIT_DIR="$SCRIPTS_DIR/2-主服务"
FILE="$HERE/servers.yaml"
DRY=0
for a in "$@"; do
    case "$a" in
        --dry-run) DRY=1 ;;
        -h|--help) sed -n '2,10p' "$0" | sed -e 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数: $a"; exit 1 ;;
    esac
done
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

STAGE="${LOCAL_STAGE:-$HOME/.cache/codebiu-update/web}"
log "===== 更新前端 → $TARGET:$REMOTE_DIR/nginx/html/index ====="

if [ "$DRY" = 1 ]; then
    log "[dry-run] 构建前端 → $STAGE"
    log "[dry-run] rsync $STAGE/ → $TARGET:$REMOTE_DIR/nginx/html/index.new/"
    log "[dry-run] 远端: mv index index_<时间戳> && mv index.new index"
    exit 0
fi

build_frontend "$STAGE"

log "[1/2] 上传静态产物"
rsync -az --delete -e "$RSYNC_RSH" "$STAGE/" "$TARGET:$REMOTE_DIR/nginx/html/index.new/"

log "[2/2] 原子切换目录"
remote "cd '$REMOTE_DIR/nginx/html' && { [ -d index ] && mv index \"index_\$(date +%Y%m%d_%H%M%S)\" || true; } && mv index.new index"
log "完成：前端已更新（旧版本保留为 index_<时间戳>，nginx 无需 reload）"
