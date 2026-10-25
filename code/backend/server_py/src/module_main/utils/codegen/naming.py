"""代码生成器命名工具: 表名/字段名到模块名、类名、变量名的推导

统一约定:
    - 模块名使用 snake_case(如 ``sys_user`` -> ``user``)
    - 类名使用 PascalCase(如 ``sys_user`` -> ``SysUser``)
    - 路由前缀为模块名复数(如 ``user`` -> ``/users``)
"""

import json
import re
from dataclasses import dataclass

# 生成模块时去除的公共表名前缀
COMMON_PREFIXES: tuple[str, ...] = ("sys_", "main_", "tpl_")

# 常见 Python 类型 -> TS 类型
TS_TYPES: dict[str, str] = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "datetime": "string",
    "date": "string",
    "time": "string",
    "json": "Record<string, unknown>",
    "bytes": "string",
}


@dataclass(slots=True)
class DerivedNames:
    """由表名推导出的命名集合"""

    module_name: str
    class_name: str
    var_name: str
    route_prefix: str
    removed_prefix: str | None = None


def to_snake(value: str) -> str:
    """
    驼峰/帕斯卡/中划线命名统一转小写下划线

    :param value: 原始名称
    :return: snake_case 名称
    """
    if not value:
        return ""
    name = value.strip().replace("-", "_").replace(" ", "_")
    # CamelCase -> snake_case(两步拆分连续大写缩写, 如 SysUser/HTTPServer)
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"_+", "_", name).strip("_").lower()


def sanitize_snake(value: str | None) -> str:
    """
    清洗为可安全用于模块名/文件名的 snake_case

    :param value: 原始输入
    :return: 仅含字母数字下划线的 snake_case, 非法输入返回空串
    """
    snake = re.sub(r"[^0-9a-z_]", "_", to_snake(value or ""))
    snake = re.sub(r"_+", "_", snake).strip("_")
    if snake and snake[0].isdigit():
        snake = f"t_{snake}"
    return snake


def to_pascal(value: str) -> str:
    """
    snake_case/驼峰命名转 PascalCase

    :param value: 原始名称
    :return: PascalCase 名称
    """
    parts = [p for p in re.split(r"[_\-\s]+", value.strip()) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def sanitize_pascal(value: str | None) -> str:
    """
    清洗为可安全用于类名的 PascalCase

    :param value: 原始输入
    :return: 仅含字母数字的 PascalCase, 非法输入返回空串
    """
    pascal = re.sub(r"[^0-9A-Za-z]", "", to_pascal(value or ""))
    if pascal and pascal[0].isdigit():
        pascal = f"T{pascal}"
    return pascal


def to_camel(value: str) -> str:
    """
    snake_case 转 camelCase

    :param value: 原始名称
    :return: camelCase 名称
    """
    pascal = to_pascal(value)
    return pascal[:1].lower() + pascal[1:] if pascal else ""


def strip_common_prefix(table_name: str) -> tuple[str, str | None]:
    """
    去除公共表名前缀

    :param table_name: 表名
    :return: (去前缀后的名称, 被去掉的前缀)
    """
    snake = to_snake(table_name)
    for prefix in COMMON_PREFIXES:
        if snake.startswith(prefix) and len(snake) > len(prefix):
            return snake[len(prefix) :], prefix
    return snake, None


def pluralize(name: str) -> str:
    """
    模块名转路由复数形式(简单英文规则)

    :param name: 模块名
    :return: 复数模块名
    """
    if not name:
        return name
    if name.endswith(("s", "x", "z", "ch", "sh")):
        return f"{name}es"
    if name.endswith("y") and len(name) > 1 and name[-2] not in "aeiou":
        return f"{name[:-1]}ies"
    return f"{name}s"


def derive_names(table_name: str) -> DerivedNames:
    """
    由表名推导模块名/类名/变量名/路由前缀

    :param table_name: 数据库表名
    :return: 命名集合(模块名去掉公共前缀, 类名取全表名 PascalCase)
    """
    snake = to_snake(table_name)
    stripped, removed = strip_common_prefix(table_name)
    module_name = sanitize_snake(stripped) or sanitize_snake(snake) or "generated"
    class_name = sanitize_pascal(snake) or sanitize_pascal(module_name) or "Generated"
    return DerivedNames(
        module_name=module_name,
        class_name=class_name,
        var_name=module_name,
        route_prefix=pluralize(module_name),
        removed_prefix=removed,
    )


def python_annotation(py_type: str, nullable: bool = False) -> str:
    """
    生成 Python 类型注解

    :param py_type: 归一化类型(str/int/float/bool/datetime/date/time/json/bytes)
    :param nullable: 是否允许为空
    :return: 如 ``str | None``
    """
    mapping = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "datetime": "datetime",
        "date": "date",
        "time": "time",
        "json": "dict",
        "bytes": "bytes",
    }
    base = mapping.get(py_type, "str")
    return f"{base} | None" if nullable else base


def ts_type(py_type: str, nullable: bool = False) -> str:
    """
    生成 TypeScript 类型

    :param py_type: 归一化类型
    :param nullable: 是否允许 null
    :return: 如 ``string | null``
    """
    base = TS_TYPES.get(py_type, "string")
    return f"{base} | null" if nullable else base


def py_literal(value: object) -> str:
    """
    Python 字面量(字符串统一用 JSON 双引号转义, 中文不转义)

    :param value: 任意值
    :return: 可直接写入源码的字面量文本
    """
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return repr(value)
