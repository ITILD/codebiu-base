# 后端工具

只放 **Dockerfile + 一次性辅助脚本**；构建、部署、发布统一走 `deveops/运维脚本/`。

| 路径 | 用途 |
| :--- | :--- |
| `docker_dev/Dockerfile.dev` | 主服务镜像（`2-主服务/build.sh` 调用） |
| `docker_task/Dockerfile.task` | 任务队列镜像（`3-任务队列/build.sh` 调用） |
| `docker_build/Dockerfile.dist` + `build.py` | Nuitka 闭源交付（可选，本地执行） |
| `cleanup_user_policies.py` | 一次性数据清理 |
| `test/` | 测试/性能辅助脚本 |

常用命令：

```bash
# 主服务
deveops/运维脚本/2-主服务/build.sh --up
deveops/运维脚本/2-主服务/update.sh

# 任务队列
deveops/运维脚本/3-任务队列/build.sh --up
deveops/运维脚本/3-任务队列/update.sh
```
