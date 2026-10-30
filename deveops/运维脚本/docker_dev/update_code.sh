#!/usr/bin/env bash
# ==============================================================================
# 日常更新(不构建镜像): 同步最新代码/配置到部署目录外挂点 -> 重启后端生效
# 依赖镜像只含 python 环境, src/config/public 全部 volume 外挂:
#   改了后端代码/配置 -> ./update_code.sh           (代码+配置+静态资源)
#   只改了配置       -> ./update_code.sh --config-only
#   改了前端         -> ./build_dist_web.sh
#   改了依赖         -> ./build_docker_server.sh --up (需重建镜像)
# ==============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cmd rsync

if [ ! -d "$DEPLOY_DIR/server_py" ]; then
    die "部署目录尚未初始化($DEPLOY_DIR), 请先执行 ./build_docker_server.sh"
fi

if [ "${1:-}" = "--config-only" ]; then
    # 只同步配置文件(不动代码)
    for f in "$BACKEND_DIR"/config*.yaml "$BACKEND_DIR/rbac_model.conf"; do
        [ -f "$f" ] || continue
        log "同步配置 $(basename "$f")"
        cp "$f" "$DEPLOY_DIR/server_py/"
    done
else
    sync_backend_runtime
fi

log "重启后端容器(外挂代码生效) ..."
# force-recreate: up -d 对配置未变的运行容器不会重启(外挂新代码不生效), 强制重建
dc up -d --force-recreate server_py
dc ps

log "更新完成, 查看日志: $DEPLOY_DIR/ctl.sh logs"
