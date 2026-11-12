"""Model 层 static_func 注册表(REQ-018): 固定规则函数作为能力供给

static_func 与 ai_model(model_config 表)平权——同一个能力解析入口既可解析到
模型也可解析到规则函数(见 module_ai/service/capability_registry.py), Skill 实现
不感知差异(设计 §2.2)。

纯函数约定: 实现禁止任何 I/O(网络/文件/DB), 同输入必同输出;
由单元测试把关(tests/module_ai/test_functions.py 断言无 I/O 触碰), 契约层不做运行时校验。
"""

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class StaticFuncDef(BaseModel):
    """静态函数能力声明(代码注册, 不入库; 版本随 git)"""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    key: str = Field(description="能力键(全局唯一, 与 ai_model 的 model_type 同一解析空间)")
    name: str = Field(max_length=100, description="展示名称")
    description: str = Field(default="", max_length=2000, description="能力说明")
    func: Callable[..., Any] = Field(description="纯函数实现(禁止 I/O)")


# 全局注册表(key -> StaticFuncDef)
FUNCTIONS: dict[str, StaticFuncDef] = {}


def register_static_func(def_: StaticFuncDef) -> StaticFuncDef:
    """注册静态函数(重复同名且同声明幂等, 冲突抛错)"""
    existed = FUNCTIONS.get(def_.key)
    if existed is not None:
        if existed == def_:
            return existed
        raise ValueError(f"static_func 注册冲突: {def_.key}")
    FUNCTIONS[def_.key] = def_
    return def_


def get_static_func(key: str) -> StaticFuncDef | None:
    return FUNCTIONS.get(key)


def list_static_funcs() -> list[StaticFuncDef]:
    return list(FUNCTIONS.values())


# 导入内置纯函数(注册即生效)
from module_ai.functions import builtin as _builtin  # noqa: E402, F401
