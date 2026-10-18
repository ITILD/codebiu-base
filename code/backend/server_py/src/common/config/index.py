"""全局配置加载: 基线层 → 环境层 → 环境变量, 三级覆盖(基线工程配置规范)

层级(低 → 高, 后层覆盖前层, 嵌套 dict 深合并, list/标量整体替换):
1. config.yaml              基线层(入 git): 引导配置 + 业务组零依赖默认值, 单文件即可启动
2. config.<APP_ENV>.yaml    环境层(gitignored): .env 写 APP_ENV=dev → 自动加载 config.dev.yaml;
                            任意环境名(dev/prod/study…)复制改名即新增环境; 缺失自动跳过
3. CODEBIU_* 环境变量       键级覆盖最高优先级(容器/K8s 密钥注入):
                            CODEBIU_TOKEN__SECRET_KEY=xxx → token.secret_key

附加: CONFIG_PATH 环境变量(逗号分隔)显式指定部署覆盖文件(缺失即启动失败, 防生产静默回退);
      项目根 .env(gitignored)经 python-dotenv 自动加载, 真实环境变量优先于 .env。

业务配置归动态配置中心: token/email/file_system/db_cache/db_vector/tasks/admin/default_models
等业务组首启以 yaml 同名节为种子入库, 之后以 系统管理→通用配置页 为准(改 yaml 不再生效);
db_rel/server/dir/mineru 等引导配置始终以 yaml 为准。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dynaconf import Dynaconf
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 基线配置文件(相对启动工作目录, 与 dir/temp_source 等相对路径约定一致)
BASE_FILE = Path("config.yaml")
# 环境声明文件(gitignored): 声明 APP_ENV 等, 真实环境变量优先
DOTENV_FILE = Path(".env")
# 环境切换变量: APP_ENV=dev → config.dev.yaml
ENV_APP_ENV = "APP_ENV"
# 部署覆盖层文件环境变量(逗号分隔多个文件, 按序覆盖)
ENV_LAYER_FILES = "CONFIG_PATH"
# 键级环境变量前缀(与 Dynaconf envvar_prefix 一致)
ENV_PREFIX = "CODEBIU"

# .env 自动加载(幂等; override=False 保证真实环境变量优先, CI/容器不受影响)
if DOTENV_FILE.exists():
    load_dotenv(DOTENV_FILE, override=False)


def _deep_merge(base: dict, overlay: dict) -> dict:
    """递归深合并: 双方均为 dict 时逐键递归, 其余(list/标量)以 overlay 整体覆盖"""
    merged = {**base}
    for key, value in overlay.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_layer(file: Path) -> dict:
    """读取单个 yaml 层(顶层必须为键值映射, 空文件视为空层)"""
    with file.open("r", encoding="utf-8") as fp:
        layer = yaml.safe_load(fp) or {}
    if not isinstance(layer, dict):
        raise ValueError(f"配置文件 {file} 顶层必须是键值映射")
    return layer


def _resolve_layer_files(base: Path = BASE_FILE) -> list[Path]:
    """解析层级文件清单: 基线 → 环境层(APP_ENV) → 部署层(CONFIG_PATH)

    - 基线缺失即失败(必须在 server_py 目录下启动)
    - 环境层缺失属正常(告警跳过, 全新项目直接用基线)
    - 部署层显式指定, 缺失即失败(防止生产静默回退基线)
    """
    if not base.exists():
        raise FileNotFoundError(f"基线配置文件不存在: {base} (需在 server_py 目录下启动)")

    files = [base]

    # 环境层: APP_ENV=dev → config.dev.yaml
    app_env = os.getenv(ENV_APP_ENV, "").strip()
    if app_env:
        file = Path(f"config.{app_env}.yaml")
        if file.exists():
            files.append(file)
        else:
            logger.warning(f"APP_ENV={app_env} 的环境配置 {file} 不存在, 已跳过")

    # 部署层: 显式指定, 即时校验(缺失即失败)
    for raw in os.getenv(ENV_LAYER_FILES, "").split(","):
        name = raw.strip()
        if not name:
            continue
        file = Path(name)
        if not file.exists():
            raise FileNotFoundError(f"CONFIG_PATH 指定的配置文件不存在: {file}")
        files.append(file)

    logger.info("配置层: %s", " → ".join(str(f) for f in files))
    return files


def _build_conf() -> Dynaconf:
    """构建全局配置单例: 各层深合并后注入, 再 execute_loaders 补跑环境变量

    环境变量必须最后执行才能保持最高优先级(update 注入数据的优先级高于 init 期加载)。
    """
    merged: dict = {}
    for file in _resolve_layer_files():
        merged = _deep_merge(merged, _read_layer(file))

    conf = Dynaconf(envvar_prefix=ENV_PREFIX)
    conf.update(merged)
    conf.execute_loaders()
    return conf


conf = _build_conf()
# 开发环境标识(影响系统 log\数据库 log 的级别和模式)
is_dev: bool = conf.state.is_dev

if __name__ == "__main__":
    print(conf.state.is_dev)
