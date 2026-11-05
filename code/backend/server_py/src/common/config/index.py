"""配置加载: 基线 + 覆盖文件 + 环境变量

优先级(低 → 高):
1. config.yaml       基线层(入 git): 通用默认值, 并用 config.local_file 指定覆盖文件
2. config.**.yaml    覆盖层(gitignored): 默认 config.dev.yaml, 写真实数据库地址/密钥
3. CODEBIU_* 环境变量 最高优先级(容器/K8s 注入), 如 CODEBIU_TOKEN__SECRET_KEY=xxx

覆盖文件由 config.yaml 的 config.local_file 决定(部署时换成任意 config.**.yaml 即可);
显式指定却不存在时直接报错(防部署静默回退基线); 文件均相对启动目录(server_py)解析。
两层文件一次加载, 嵌套 dict 由 Dynaconf 深合并。
业务组首启以 yaml 同名节为种子入库, 之后以 系统管理→通用配置页 为准(改 yaml 不再生效);
db_rel/server/dir/mineru 等引导配置始终以 yaml 为准。
"""
from __future__ import annotations

import logging
from pathlib import Path

from dynaconf import Dynaconf

logger = logging.getLogger(__name__)

BASE_FILE = Path("config.yaml")
LOCAL_FILE_KEY = "config.local_file"


def _settings_files() -> list[Path]:
    """基线必选; 覆盖文件由 config.yaml 的 config.local_file 指定"""
    if not BASE_FILE.exists():
        raise FileNotFoundError(
            f"基线配置文件不存在: {BASE_FILE} (需在 server_py 目录下启动)"
        )

    name = str(
        Dynaconf(settings_files=[BASE_FILE], environments=False).get(LOCAL_FILE_KEY) or ""
    ).strip()
    if not name:
        logger.warning("config.yaml 未配置 config.local_file, 仅加载基线")
        return [BASE_FILE]

    path = Path(name)
    if not path.exists():
        raise FileNotFoundError(f"config.local_file 指定的配置文件不存在: {path}")

    logger.info("配置层: %s → %s", BASE_FILE, path)
    return [BASE_FILE, path]


def _load(files: list[Path]) -> Dynaconf:
    """按文件顺序加载, 后者覆盖前者, 嵌套 dict 深合并"""
    return Dynaconf(
        envvar_prefix="CODEBIU",  # CODEBIU_TOKEN__SECRET_KEY → token.secret_key
        settings_files=files,
        environments=False,  # 不启用 dynaconf 的 [default]/[dev] 节
        merge_enabled=True,  # 多文件合并时保留未覆盖的同级键
    )


conf = _load(_settings_files())
# 开发环境标识(影响系统 log/数据库 log 的级别和模式)
is_dev: bool = conf.state.is_dev

if __name__ == "__main__":
    print(is_dev)

