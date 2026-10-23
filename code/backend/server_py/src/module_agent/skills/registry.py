"""技能(Skill)注册表: 智能体可调用的原子能力声明与查找(REQ-013)

- SkillDef: 单个技能的元信息 + 参数模型 + 执行函数
- SKILLS: 模块级注册表(进程内唯一, 声明式零开销)
- 能力分级: read 只读(默认)/write 写入(本期无, 供后续扩展展示)
"""

from enum import StrEnum
from typing import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field


class SkillCapability(StrEnum):
    """技能能力分级"""

    READ = "read"  # 只读技能(检索/识别, 不改变系统状态)
    WRITE = "write"  # 写入技能(创建任务/生成文件等, 本期未启用)


class SkillContext(BaseModel):
    """技能执行上下文(每次智能体运行构造一次, 无跨请求共享状态)"""

    user_id: str = Field(description="当前用户ID(底层服务按其解析模型/权限)")
    # 助手配置的默认知识库ID列表(技能参数未显式指定时回退)
    default_project_ids: list[str] = Field(default_factory=list)


class SkillArgs(BaseModel):
    """技能参数基类(空, 具体技能自行派生)"""


class SkillDef(BaseModel):
    """技能定义(LLM 工具调用的统一封装)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(description="技能注册名(即 LLM 工具名, 全局唯一)")
    display_name: str = Field(description="展示名称")
    # 给 LLM 的能力说明(bind_tools 时作为工具 description)
    description: str = Field(description="能力描述(供 LLM 判断何时调用)")
    capability: SkillCapability = Field(default=SkillCapability.READ, description="能力分级")
    args_model: type[BaseModel] = Field(description="参数模型(JSON Schema 派生)")
    func: Callable[[BaseModel, SkillContext], Awaitable[str]] = Field(
        description="执行函数: (args, ctx) -> 文本结果(回填 ToolMessage)"
    )


# 全局注册表(name -> SkillDef); builtin 声明后自动写入
SKILLS: dict[str, SkillDef] = {}


def register_skill(skill: SkillDef) -> None:
    """注册技能(重名覆盖, 便于测试替身)"""
    SKILLS[skill.name] = skill


def get_skill(name: str) -> SkillDef | None:
    """按名查找技能"""
    return SKILLS.get(name)


def list_skill_infos() -> list[dict]:
    """技能清单(注册顺序, 供前端管理页/助手编辑器展示)"""
    return [
        {
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "capability": s.capability.value,
        }
        for s in SKILLS.values()
    ]
