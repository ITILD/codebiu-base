#!/bin/bash
# 启动部署目录中的全部服务(薄封装, 统一入口: deveops/运维脚本/docker_dev)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../../../../../deveops/运维脚本/docker_dev/lib.sh"
dc up -d && dc ps
