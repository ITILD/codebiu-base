"""成本与用量治理 REST 路由(挂载 /rag/usage), 管理端点仅系统管理员。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.utils.db.schema.pagination import PaginationParams
from module_authorization.config.casbin_rule import auth_manager
from module_authorization.dependencies.auth import get_current_user_id
from module_rag.config.server import module_app
from module_rag.service.conversation import ConversationService
from module_rag.service.usage import ChatUsageService

router = APIRouter()


def _is_admin(user_id: str) -> bool:
    """判断用户是否为全局管理员(与 module_rag.controller.project_document_chunk 同规则)"""
    enforcer = auth_manager.enforcer
    if enforcer is None:
        return False
    return bool(enforcer.has_grouping_policy(user_id, "admin", "*"))


async def require_admin(
    current_user_id: str = Depends(get_current_user_id),
) -> str:
    """依赖: 仅系统管理员可通过(全局域 admin 角色)"""
    if not _is_admin(current_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="仅系统管理员可访问"
        )
    return current_user_id


@router.get("/stats", summary="用量统计(成本与用量治理)")
async def get_usage_stats(
    days: int = Query(default=30, ge=1, le=366, description="统计天数(含当天)"),
    user_id: str | None = Query(default=None, description="按用户过滤(可选)"),
    top_n: int = Query(default=10, ge=1, le=100, description="用户排行返回条数"),
    _: str = Depends(require_admin),
) -> dict:
    """问答 token 用量与成本统计: 汇总卡/每日趋势/用户排行/模型分布"""
    try:
        return await ChatUsageService().stats(days=days, user_id=user_id, top_n=top_n)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records", summary="用量明细分页(成本与用量治理)")
async def get_usage_records(
    pagination: PaginationParams = Depends(),
    days: int | None = Query(default=None, ge=1, le=366, description="统计天数过滤(可选)"),
    user_id: str | None = Query(default=None, description="按用户过滤(可选)"),
    model_name: str | None = Query(default=None, description="按模型标识模糊过滤(可选)"),
    _: str = Depends(require_admin),
):
    """问答 token 用量与成本明细(时间倒序, 补齐用户名)"""
    try:
        return await ChatUsageService().list_records(
            pagination, days=days, user_id=user_id, model_name=model_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations", summary="对话用量聚合分页(对话记录)")
async def get_usage_conversations(
    pagination: PaginationParams = Depends(),
    user_id: str | None = Query(default=None, description="按用户过滤(可选)"),
    _: str = Depends(require_admin),
):
    """对话维度 token/成本聚合列表(最近活跃倒序, 补齐标题与用户名)"""
    try:
        return await ChatUsageService().list_conversations(pagination, user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last", summary="最近一轮问答用量(用户自查)")
async def get_last_usage(
    conversation_id: str = Query(..., description="会话ID"),
    current_user_id: str = Depends(get_current_user_id),
):
    """当前用户在指定会话最近一轮的 token 与费用(仅本人会话可查)"""
    conv = await ConversationService().get(conversation_id)
    if conv is None or conv.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该会话用量"
        )
    usage = await ChatUsageService().last_usage(current_user_id, conversation_id)
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": (usage.prompt_tokens or 0) + (usage.completion_tokens or 0),
        "cost": usage.cost,
        "model_name": usage.model_name,
        "mode": usage.mode,
        "created_at": usage.created_at,
    }


# 注册路由
module_app.include_router(router, prefix="/usage", tags=["成本与用量治理"])
