"""权限认证模块 auth 接口层: 参数校验并调度 service"""

from fastapi import APIRouter, Depends, Form, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from common.utils.fastapi_ex.exceptions import UnauthorizedError
from module_authorization.do.token import (
    RefreshTokenRequest,
    TokenResponseFull,
    TokenResponseBase,
)
from module_authorization.config.server import module_app
from module_authorization.service.auth import AuthService
from module_authorization.service.avatar import AvatarService
from module_authorization.dependencies.auth import (
    get_auth_service,
    get_current_user,
    get_current_user_id
)
from module_authorization.dependencies.avatar import get_avatar_service
from module_authorization.dependencies.user_preference import get_user_preference_service
from module_authorization.service.user_preference import UserPreferenceService
from module_authorization.do.user_preference import UserPreferenceUpdate, UserPreferenceResponse
from module_authorization.do.user import UserCreate,User
from module_authorization.do.auth import AuthResponse,AuthLogoutRequest,SelfProfileUpdate,PasswordChange
from module_authorization.do.auth import (
    LoginCodeRequest,
    LoginPolicyResponse,
    RegisterCodeRequest,
    RegisterConfigResponse,
    RegisterRequest,
)
from module_authorization.config.register import email_verify_enabled
from common.config.dynamic import get_settings
from common.config.dynamic.schemas import LoginSecuritySettings

# 创建路由器
router = APIRouter()


@router.get("/me", summary="获取当前登录用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    """根据访问令牌返回当前登录用户的完整信息"""
    return current_user

@router.get("/me-id", summary="获取当前登录用户ID")
async def get_me_id(current_user_id: str = Depends(get_current_user_id)):
    """根据访问令牌返回当前登录用户的ID(轻量级身份校验)"""
    return current_user_id


@router.get("/me/preference", summary="获取当前用户样式配置")
async def get_my_preference(
    current_user_id: str = Depends(get_current_user_id),
    service: UserPreferenceService = Depends(get_user_preference_service),
) -> UserPreferenceResponse:
    """返回当前登录用户保存的样式配置(未设置时返回默认 auto, 登录即可调用)"""
    return await service.get(current_user_id)


@router.put("/me/preference", summary="保存当前用户样式配置")
async def update_my_preference(
    preference: UserPreferenceUpdate,
    current_user_id: str = Depends(get_current_user_id),
    service: UserPreferenceService = Depends(get_user_preference_service),
) -> UserPreferenceResponse:
    """保存当前登录用户的样式配置(主题模式主题值非法时返回400, 登录即可调用)"""
    # service 校验失败抛 ValueError, 由全局处理器统一映射为 400
    return await service.save(current_user_id, preference)


@router.put("/me", summary="自助更新个人资料")
async def update_my_profile(
    profile: SelfProfileUpdate,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """当前登录用户修改自己的昵称/邮箱/电话/头像(无需管理员权限)"""
    # service 校验失败抛 ValueError, 由全局处理器统一映射为 400
    return await auth_service.update_my_profile(current_user.id, profile)


@router.put(
    "/me/password", summary="自助修改密码", status_code=status.HTTP_204_NO_CONTENT
)
async def change_my_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """当前登录用户修改自己的密码(需验证旧密码,成功后返回204)"""
    # service 校验失败(用户不存在/旧密码错误/新旧相同)抛 ValueError, 由全局处理器映射为 400
    await auth_service.change_my_password(
        current_user.id,
        password_change.old_password,
        password_change.new_password,
    )


@router.post("/me/avatar", summary="上传当前用户头像")
async def upload_my_avatar(
    file: UploadFile = File(..., description="头像图片文件,支持 png/jpg/jpeg/gif/webp/svg/bmp"),
    current_user: User = Depends(get_current_user),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    """
    上传当前登录用户的头像(登录即可,无需权限码)
    头像经统一文件服务存入虚拟目录 /用户头像/<用户ID>/ 下, 并自动清理旧头像条目;
    下载走 /file/filesystem/download/{entry_id}(avatar 来源允许匿名访问)
    :param file: 图片文件(png/jpg/jpeg/gif/webp/svg/bmp)
    :return: {"avatar": 下载路径, "entry_id": 文件条目ID}
    """
    # 文件校验失败抛 ValueError, 由全局处理器映射为 400
    return await avatar_service.upload_avatar(current_user.id, file)


@router.delete(
    "/me/avatar",
    summary="删除当前用户头像(还原默认首字头像)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_my_avatar(
    current_user: User = Depends(get_current_user),
    avatar_service: AvatarService = Depends(get_avatar_service),
):
    """
    删除当前登录用户的头像并还原默认(用户名首字头像, 登录即可无需权限码)
    服务端清理 avatar 模块的头像文件条目并置空用户头像字段
    """
    # 头像不存在等校验失败抛 ValueError, 由全局处理器映射为 400
    await avatar_service.delete_avatar(current_user.id)

@router.get("/me-permissions", summary="获取当前用户的角色与权限码")
async def get_my_permissions(
    current_user_id: str = Depends(get_current_user_id),
    auth_service: AuthService = Depends(get_auth_service),
):
    """获取当前用户的角色(按域分组)与权限码列表(登录用户即可调用,仅能查看自己)"""
    return await auth_service.get_user_permission_info(current_user_id)


@router.get("/register-config", summary="获取注册流程配置")
async def get_register_config() -> RegisterConfigResponse:
    """返回注册流程配置(是否开启邮箱验证码),供前端决定注册弹窗是否展示验证码输入"""
    return RegisterConfigResponse(email_verify=await email_verify_enabled())


@router.post("/register/code", summary="发送注册邮箱验证码")
async def send_register_code(
    code_request: RegisterCodeRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> bool:
    """向指定邮箱发送注册验证码:仅开启 email.use_for_register 时可用,
    同一邮箱60秒内限发一次,验证码5分钟内有效且校验通过后立即失效
    """
    # 未开启邮箱验证/发送过于频繁/邮件发送失败抛 ValueError, 由全局处理器映射为 400
    return await auth_service.send_register_code(code_request.email)


@router.post("/register", summary="注册用户")
async def register_user(
    register_request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    """注册新用户并直接返回登录态:校验用户名唯一(重复时报400)
    密码加密存储,首个注册用户自动引导为全局管理员,成功返回 access/refresh 双令牌与用户信息
    开启邮箱验证(email.use_for_register)时需先调 /register/code 获取验证码并随请求提交
    """
    # 用户名重复/验证码错误等校验失败抛 ValueError, 由全局处理器映射为 400
    user_create = UserCreate(**register_request.model_dump(exclude={"code"}))
    return await auth_service.register(user_create, register_request.code)

@router.get("/login-policy", summary="获取登录流程配置")
async def get_login_policy() -> LoginPolicyResponse:
    """返回登录流程配置(是否开启二次验证码),供前端决定登录弹窗是否展示验证码输入"""
    # 匿名可访问: 登录前展示表单所需(仅暴露开关, 不含阈值等其余安全参数)
    sec = await get_settings(LoginSecuritySettings)
    return LoginPolicyResponse(mfa_enabled=sec.mfa_enabled)


@router.post("/login/code", summary="发送登录二次验证邮箱验证码")
async def send_login_code(
    code_request: LoginCodeRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> bool:
    """向登录用户绑定邮箱发送二次验证码:仅开启 login_security.mfa_enabled 时可用,
    同一邮箱60秒内限发一次,验证码5分钟内有效且校验通过后立即失效
    """
    # 未开启二次验证/用户不存在/发送过于频繁抛 ValueError, 由全局处理器映射为 400
    return await auth_service.send_login_code(code_request.username)


@router.post("/login", summary="登录获取访问令牌")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    code: str | None = Form(default=None, description="登录二次验证码(开启时必填)"),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    """校验用户名密码并签发登录态:凭据错误/账户锁定或被禁用时返回401
    开启登录失败锁定(login_security.lock_enabled)后连续失败达阈值将锁定账户一段时间;
    开启二次验证(mfa_enabled)时需先调 /login/code 获取验证码并随表单提交
    成功返回 access/refresh 双令牌与用户信息
    """
    try:
        token_response = await auth_service.login(form_data.username, form_data.password, code)
    except ValueError as e:
        # 凭据错误/账户锁定/禁用/验证码错误 -> 401; 其余意外异常交由全局处理器兜底 500
        raise UnauthorizedError(str(e))
    return token_response


@router.post("/token", summary="OAuth2 标准登录(Swagger Authorize 专用) 调试使用")
async def login_for_oauth2(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """
    OAuth2 Password 流程标准端点,供 Swagger UI "Authorize" 按钮使用
    响应为标准格式 {"access_token": ..., "token_type": "bearer"},
    Swagger 才能自动提取并携带令牌调用其他接口;前端请继续使用 /login
    """
    try:
        token_response = await auth_service.login(form_data.username, form_data.password)
    except ValueError as e:
        # 凭据错误/账户禁用 -> 401
        raise UnauthorizedError(str(e))
    return {
        "access_token": token_response.tokens.access.token,
        "token_type": "bearer",
    }

@router.post("/logout", summary="登出")
async def logout(
    logout_request: AuthLogoutRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> bool:
    """登出并吊销令牌:访问令牌无效或已吊销时返回401(防止重复登出)
    校验通过后将访问令牌写入Redis黑名单立即失效,并撤销配套刷新令牌(刷新令牌无效不阻断登出)
    """
    try:
        await auth_service.logout(logout_request)
    except ValueError as e:
        # 访问令牌无效/已吊销 -> 401
        raise UnauthorizedError(str(e))
    return True

@router.post("/refresh", summary="刷新访问令牌")
async def refresh_access_token(
    refresh_token_request: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponseBase:
    """校验刷新令牌并签发新的访问令牌(刷新令牌本身不轮换)
    刷新令牌无效或已吊销时返回401,账户被禁用时拒绝刷新
    """
    try:
        token_response = await auth_service.token_refresh(refresh_token_request.token_refresh)
    except ValueError as e:
        # 刷新令牌无效/已吊销/账户禁用 -> 401(原代码捕获 HTTPException 属死代码, service 实际抛 ValueError)
        raise UnauthorizedError(str(e))
    return token_response

# 注册登录
module_app.include_router(router, prefix="/auth")
