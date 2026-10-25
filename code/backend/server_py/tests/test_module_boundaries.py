"""模块依赖方向守门测试(Phase 0/1 契约)

设计约束: 依赖只允许 ``module_rag → module_office → module_ai``。

- ai 不得感知 office/rag 的文件与知识库概念
- office 不得感知 rag 业务, 且只允许通过 ai 的 service/dependencies 使用 ai 能力
- 各模块只允许 controller/service/dao/do/dependencies/config/utils 七类目录
- rag 对 office/ai 的收口(禁止直接引用 office.utils/service)属 Phase 4, 暂不在此断言

采用 AST 静态扫描而非运行时导入, 避免测试触发数据库/网络初始化。
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

# 已知债务(Phase 4 清除): ModelEntryService 延迟导入 rag 的用户模型绑定解析
_PENDING_DEBT = {
    ("module_ai/service/model_config.py", "module_rag.service.user_model"),
}


def _module_files(module: str) -> list[Path]:
    """返回模块下全部 Python 文件"""
    return sorted((SRC / module).rglob("*.py"))


def _imports(path: Path) -> list[str]:
    """收集文件内全部绝对导入(含函数内延迟导入)"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


def _violations(module: str, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    """按模块扫描违规导入, 返回 "文件: 导入" 形式的问题清单"""
    problems: list[str] = []
    for path in _module_files(module):
        rel = f"{module}/{path.relative_to(SRC / module).as_posix()}"
        for name in _imports(path):
            if not name.startswith(forbidden_prefixes):
                continue
            if (rel, name) in _PENDING_DEBT:
                continue
            problems.append(f"{rel}: {name}")
    return problems


def test_ai_must_not_depend_on_office():
    """ai 是能力层, 不得反向依赖 office"""
    problems = _violations("module_ai", ("module_office",))
    assert not problems, "module_ai 反向依赖 module_office:\n" + "\n".join(problems)


def test_ai_must_not_depend_on_rag():
    """ai 是能力层, 不得依赖知识库业务"""
    problems = _violations("module_ai", ("module_rag",))
    assert not problems, "module_ai 反向依赖 module_rag:\n" + "\n".join(problems)


def test_office_must_not_depend_on_rag():
    """office 是文档处理层, 不得依赖知识库业务"""
    problems = _violations("module_office", ("module_rag",))
    assert not problems, "module_office 反向依赖 module_rag:\n" + "\n".join(problems)


def test_office_uses_ai_only_through_service():
    """office 只能通过 service/dependencies 使用 ai 能力, 不得触碰内部实现"""
    allowed = ("module_ai.service", "module_ai.dependencies")
    problems: list[str] = []
    for path in _module_files("module_office"):
        rel = f"module_office/{path.relative_to(SRC / 'module_office').as_posix()}"
        for name in _imports(path):
            if not name.startswith("module_ai"):
                continue
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in allowed):
                continue
            problems.append(f"{rel}: {name}")
    assert not problems, (
        "module_office 越过契约直接引用 module_ai 内部实现:\n" + "\n".join(problems)
    )


def test_no_parallel_api_directory():
    """controller 即 api 层: 禁止再建 api/ 平行目录(对象进 do, 契约随实现进 service)"""
    offenders = sorted(
        path.relative_to(SRC).as_posix() for path in SRC.glob("module_*/api")
    )
    assert not offenders, "存在非规范 api/ 目录, 请合并进 controller/service/do:\n" + "\n".join(
        offenders
    )


def test_pending_debt_is_still_accurate():
    """债务清单必须在 Phase 4 清理; 已消失的条目要同步删除, 防止列表失真"""
    for rel, name in _PENDING_DEBT:
        path = SRC / rel
        assert path.exists(), f"债务文件已不存在, 请更新清单: {rel}"
        assert name in _imports(path), f"债务已消除, 请从清单移除: {rel} -> {name}"
