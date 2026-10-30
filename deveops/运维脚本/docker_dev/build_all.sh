#!/usr/bin/env bash
# ==============================================================================
# 一键: 后端镜像 -> 前端 dist -> 部署目录 -> 启动/更新容器
# 任何 Ubuntu 电脑(装好 docker)克隆仓库后直接: ./build_all.sh
# 可选环境变量:
#   SKIP_WEB=1     跳过前端构建(只更后端)
#   SKIP_SERVER=1  跳过后端镜像构建(只更前端)
#   DEPLOY_DIR=... 覆盖部署目录(见 deploy.env)
# ==============================================================================
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cmd docker
require_cmd rsync

log "部署目录: $DEPLOY_DIR (改配置: deveops/运维脚本/docker_dev/deploy.env)"

# ---------- 1. 后端: 构建镜像 + 初始化部署目录 + 同步外挂 ----------
if [ "${SKIP_SERVER:-0}" != "1" ]; then
    "$DEVOPS_DIR/build_docker_server.sh"
else
    log "跳过后端镜像构建(SKIP_SERVER=1), 仅初始化部署目录"
    init_deploy_dir "$(resolve_server_image)"
    sync_backend_runtime
fi

# ---------- 2. 前端: 容器内构建 dist 导出到 nginx 目录 ----------
if [ "${SKIP_WEB:-0}" != "1" ]; then
    "$DEVOPS_DIR/build_dist_web.sh"
else
    log "跳过前端构建(SKIP_WEB=1)"
fi

# ---------- 3. 启动/更新容器(外挂内容变化会重建对应容器) ----------
log "启动/更新容器 ..."
dc up -d
# 外挂后端代码非热加载(uvicorn 无 --reload): up -d 对配置未变的容器不会重启,
# 强制重建 server 容器让同步的新代码生效(前端 dist 由 nginx 读卷, 无需重启)
dc up -d --force-recreate server_py
dc ps

log "全部完成: 前端 http://localhost:$NGINX_PORT | 后端 http://localhost:$SERVER_PORT"
log "日常更新代码只需: ./update_code.sh ; 部署机操作: $DEPLOY_DIR/ctl.sh"
