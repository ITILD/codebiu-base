"""权限认证模块 auth FastAPI 依赖注入"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from module_authorization.service.auth import AuthService
from module_authorization.service.user import UserService
from module_authorization.service.token import TokenService
from module_authorization.dependencies.user import get_user_service
from module_authorization.dependencies.token import get_token_service
from module_contact.service.verify_code import VerifyCodeService, get_verify_code_service

# 不做业务验证：oauth2_scheme 不验证 Token 的有效性、过期时间或签名。它只负责“搬运”字符串。
# OAuth2 scheme(tokenUrl 指向 OAuth2 标准响应端点,Swagger Authorize 才能自动提取令牌)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/authorization/auth/token")


async def get_auth_service(
    user_service: UserService = Depends(get_user_service),
    token_service: TokenService = Depends(get_token_service),
    verify_code_service: VerifyCodeService = Depends(get_verify_code_service),
):
    """AuthService工厂函数(注入用户/令牌/验证码服务, 验证码由 module_contact 提供邮件/短信触达)"""
    return AuthService(user_service, token_service, verify_code_service)


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
):
    """获取当前用户"""
    try:
        user = await auth_service.get_current_user(token)
        # 写入 request.state 供审计中间件读取操作人(REQ-009)
        request.state.user_id = user.id
        return user

    except Exception as e:
        # 捕获所有其他异常，确保错误信息能够传递给前端
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def get_current_user_id(
    request: Request,
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
):
    """获取当前用户ID"""
    try:
        user_id = await auth_service.get_current_user_id(token)
        # 写入 request.state 供审计中间件读取操作人(REQ-009)
        request.state.user_id = user_id
        return user_id
    except Exception as e:
        # 捕获所有其他异常，确保错误信息能够传递给前端
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def get_current_user_id_optional(
    request: Request,
    token: str | None = Depends(
        OAuth2PasswordBearer(tokenUrl="/authorization/auth/token", auto_error=False)
    ),
    auth_service: AuthService = Depends(get_auth_service),
) -> str | None:
    """获取当前用户ID(可选登录: 未携带或无效Token返回None,由调用方决定匿名策略)"""
    if not token:
        return None
    try:
        user_id = await auth_service.get_current_user_id(token)
        if user_id:
            request.state.user_id = user_id
        return user_id
    except Exception:
        return None
