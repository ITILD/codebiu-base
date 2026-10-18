"""服务器环境信息采集"""

from pathlib import Path

_PATH_CWD = Path.cwd()

def get_rel_path(path:Path):
    try:
        return path.relative_to(_PATH_CWD)
    except ValueError:
        return path  # 不在项目内则返回原路径
    