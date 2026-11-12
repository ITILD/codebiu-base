"""能力注册表 API(REQ-018): Model 层双源能力视图(ai_model + static_func)

GET /ai/capabilities  能力清单(static_func 代码注册表 + 各 model_type 可解析性),
登录可见 —— 模型能力中心的「供给侧」视图; Skill 的 model_bindings/required
引用的 capability_key 均可在此核对解析结果。
"""

from fastapi import APIRouter, Depends

from module_ai.service.capability_registry import list_capabilities
from module_authorization.dependencies.permission import get_current_user_id

from module_ai.config.server import module_app

router = APIRouter()


@router.get("/capabilities", summary="能力注册表(双源合一)")
async def get_capabilities(
    current_user_id: str = Depends(get_current_user_id),
) -> list[dict]:
    """能力清单: static_func(规则函数) + ai_model(各类型三作用域解析结果)"""
    return await list_capabilities(current_user_id)


module_app.include_router(router, tags=["能力注册表"])
