#!/bin/bash
# 构建后端镜像并同步外挂代码(薄封装, 统一入口: deveops/运维脚本/docker_dev/build_docker_server.sh)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/../../../../../deveops/运维脚本/docker_dev/build_docker_server.sh" "$@"
