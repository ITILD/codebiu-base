#!/bin/bash
# 停止并移除容器(数据在部署目录宿主机侧, 不丢; 薄封装, 统一入口: deveops/运维脚本/docker_dev)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../../../../../deveops/运维脚本/docker_dev/lib.sh"
dc down
