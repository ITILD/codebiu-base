#!/usr/bin/env bash
# ==============================================================================
# 日常更新任务队列（不重建镜像）：同步代码/配置 -> 重启 worker/beat
# 改了依赖才需要重新执行 ./build.sh
# ==============================================================================
source "$(dirname "$0")/../lib.sh"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 服务器角色配置：server_1（112 任务队列机）
ENV_FILE="${DEPLOY_ENV:-$KIT_DIR/server_1/deploy.env}"
[ -f "$ENV_FILE" ] || die "缺少配置 $ENV_FILE"
# shellcheck disable=SC1091
source "$ENV_FILE"

require_cmd rsync
[ -d "$DEPLOY_DIR/app" ] || die "部署目录尚未初始化，请先执行 ./build.sh"

sync_backend "$DEPLOY_DIR/app"
log "重启任务 worker/beat ..."
"$DEPLOY_DIR/ctl.sh" restart task_worker
"$DEPLOY_DIR/ctl.sh" restart task_beat
"$DEPLOY_DIR/ctl.sh" status
