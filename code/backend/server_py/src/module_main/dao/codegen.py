"""系统主模块 代码生成器数据访问层

只读取 ``SQLModel.metadata.tables`` 中的表元数据, 不连接数据库、不执行 SQL。
项目启动时各模块 do 层模型已被导入, 因此建表前也能拿到完整表结构。
"""

from sqlalchemy import types as sa_types
from sqlmodel import SQLModel

from common.utils.fastapi_ex.exceptions import NotFoundError
from module_main.do.codegen import ColumnMeta, TableBrief, TableDetail


def _normalize_python_type(sql_type) -> str:
    """
    SQLAlchemy 字段类型归一化为 Python 类型名

    :param sql_type: SQLAlchemy TypeEngine 实例
    :return: str/int/float/bool/datetime/date/time/json/bytes
    """
    if isinstance(sql_type, sa_types.Boolean):
        return "bool"
    if isinstance(sql_type, sa_types.Integer):
        return "int"
    if isinstance(sql_type, (sa_types.Numeric, sa_types.Float)):
        return "float"
    if isinstance(sql_type, sa_types.DateTime):
        return "datetime"
    if isinstance(sql_type, sa_types.Date):
        return "date"
    if isinstance(sql_type, sa_types.Time):
        return "time"
    if isinstance(sql_type, sa_types.JSON):
        return "json"
    if isinstance(sql_type, sa_types.LargeBinary):
        return "bytes"
    return "str"


def _column_default(column) -> str | None:
    """
    取字段默认值的文本形式(可调用默认值不展开)

    :param column: SQLAlchemy Column
    :return: 默认值文本, 无默认值返回 None
    """
    default = column.default
    if default is None:
        return None
    arg = getattr(default, "arg", None)
    if arg is None or callable(arg):
        return None
    return str(arg)


class CodegenDao:
    """代码生成器数据访问对象(仅元数据读取)"""

    def list_tables(self, keyword: str | None = None) -> list[TableBrief]:
        """
        列出全部已注册模型的表元数据

        :param keyword: 按表名/表注释模糊过滤(不区分大小写)
        :return: 表清单(按表名排序)
        """
        keyword_lower = keyword.strip().lower() if keyword else ""
        items: list[TableBrief] = []
        for name, table in sorted(SQLModel.metadata.tables.items()):
            comment = table.comment
            if keyword_lower and keyword_lower not in f"{name} {comment or ''}".lower():
                continue
            items.append(
                TableBrief(
                    name=name,
                    comment=comment,
                    column_count=len(table.columns),
                )
            )
        return items

    def get_table(self, table_name: str) -> TableDetail:
        """
        获取单表元数据

        :param table_name: 表名
        :return: 表详情(含字段类型/可空/主键/默认值/注释/长度)
        :raises NotFoundError: 表不存在
        """
        name = (table_name or "").strip()
        table = SQLModel.metadata.tables.get(name)
        if table is None:
            raise NotFoundError(f"数据表不存在: {name}")
        columns: list[ColumnMeta] = []
        for column in table.columns:
            sql_type = column.type
            columns.append(
                ColumnMeta(
                    name=column.name,
                    type=_normalize_python_type(sql_type),
                    sql_type=str(sql_type),
                    nullable=bool(column.nullable),
                    primary_key=bool(column.primary_key),
                    default=_column_default(column),
                    comment=column.comment,
                    max_length=getattr(sql_type, "length", None),
                )
            )
        return TableDetail(name=name, comment=table.comment, columns=columns)
