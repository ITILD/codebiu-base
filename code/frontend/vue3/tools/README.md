# 前端工具

只放 **Dockerfile**；构建/发布统一由 `deveops/运维脚本/2-主服务/build.sh` 调用。

| 路径 | 用途 |
| :--- | :--- |
| `docker_dev/Dockerfile.dev` | 容器内 `pnpm build-only`，产物直接导出到部署目录 `nginx/html/index` |

日常无需在本机装 pnpm/Node，也不需要在此目录执行任何脚本。
