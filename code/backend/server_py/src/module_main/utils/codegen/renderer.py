"""代码生成器 Jinja2 渲染器

模板统一放在 ``module_main/utils/codegen/templates``, 使用严格的未定义变量校验,
避免模板变量缺失时生成出不可用的代码。
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# 模板目录(与本文件同级)
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# 生成的是代码而非 HTML, 关闭自动转义(模板内自行使用 Jinja 过滤器)
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR), encoding="utf-8"),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


def render(template_name: str, context: dict) -> str:
    """
    渲染指定模板

    :param template_name: 模板文件名(如 backend_do.py.j2)
    :param context: 模板上下文
    :return: 渲染后的代码文本
    """
    return _env.get_template(template_name).render(**context)


def list_templates() -> list[str]:
    """列出全部模板文件名(便于自检模板是否齐全)"""
    return sorted(_env.list_templates())
