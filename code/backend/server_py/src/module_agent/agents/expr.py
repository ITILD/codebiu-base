"""job 编排条件表达式(REQ-018, CA-07): when/skip_if 的显式安全求值

约束(设计 §2.4/§3.3): rule Agent 的分支条件必须是**显式表达式**, 禁止塞进
Skill 实现隐藏、禁止 eval 任意代码。本求值器基于 Python ast 白名单实现:

支持语法(足够批内条件表达, 不引入图灵完备):
    字面量: true/false/null/数字/'单引号字符串'/"双引号字符串"/[列表]
    引用:   name.field / name.field.field(上下文逐级取值), 缺失字段解析为 null
    比较:   ==  !=  <  <=  >  >=  in  not in
    逻辑:   and  or  not(短路)
结果必须可解释为布尔(CA-07: 分支判定可追溯, 判定结果随步骤状态落库)。
"""

import ast
from typing import Any


class ExprError(ValueError):
    """表达式非法(解析期/求值期白名单外语法)"""


def evaluate(expr: str, context: dict[str, Any]) -> bool:
    """求值条件表达式 → 布尔

    :param expr: 如 "parse.degraded == true" / "item.size_hint > 1048576"
    :param context: 引用名 → 值(如 {"parse": {...}, "item": {...}})
    :raises ExprError: 白名单外语法
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"条件表达式语法错误: {expr!r} ({e})") from e
    return bool(_eval(tree.body, context, expr))


# ── 求值器(ast 节点白名单分派) ──


def _eval(node: ast.AST, context: dict[str, Any], expr: str) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            return node.value
        raise ExprError(f"不支持的字面量类型: {type(node.value).__name__}")
    if isinstance(node, ast.Name):
        if node.id == "true":
            return True
        if node.id == "false":
            return False
        if node.id == "null":
            return None
        if node.id in context:
            return context[node.id]
        raise ExprError(f"未定义的引用: {node.id}(可用: {sorted(context)})")
    if isinstance(node, ast.Attribute):
        base = _eval(node.value, context, expr)
        if isinstance(base, dict):
            return base.get(node.attr)
        return getattr(base, node.attr, None)
    if isinstance(node, ast.List):
        return [_eval(item, context, expr) for item in node.elts]
    if isinstance(node, ast.Compare):
        left = _eval(node.left, context, expr)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, context, expr)
            if not _compare(op, left, right, expr):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for value in node.values:
                result = _eval(value, context, expr)
                if not result:
                    return result  # 短路
            return result
        result = False
        for value in node.values:  # ast.Or
            result = _eval(value, context, expr)
            if result:
                return result  # 短路
        return result
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, context, expr)
    raise ExprError(
        f"条件表达式不支持该语法: {type(node).__name__}(表达式: {expr!r})"
    )


def _compare(op: ast.cmpop, left: Any, right: Any, expr: str) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
        try:
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.LtE):
                return left <= right
            if isinstance(op, ast.Gt):
                return left > right
            return left >= right
        except TypeError as e:
            raise ExprError(f"不可比较的类型: {e}(表达式: {expr!r})") from e
    if isinstance(op, ast.In):
        return left in right
    if isinstance(op, ast.NotIn):
        return left not in right
    raise ExprError(f"不支持的比较运算: {type(op).__name__}")
