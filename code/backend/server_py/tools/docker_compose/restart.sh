#!/bin/bash
# 重启后端(默认)或指定服务: ./restart.sh [nginx|postgres|redis7|server_py]
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/../../../../../deveops/运维脚本/docker_dev/lib.sh"
dc restart "${1:-server_py}"
