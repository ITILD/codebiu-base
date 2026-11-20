"""权限认证模块 avatar 业务逻辑层"""

import logging
import re
from pathlib import Path

from fastapi import UploadFile

from common.utils.fastapi_ex.exceptions import ConflictError
from module_authorization.dao.user import UserDao
from module_authorization.do.user import UserUpdate
from module_file.do.filesystem import (
    EntryCreateRequest,
    FileEntry,
    MultipartCompleteRequest,
    MultipartInitRequest,
    MultipartInitResponse,
)
from module_file.service.filesystem import FileService

logger = logging.getLogger(__name__)

# 头像模块在虚拟目录树中的模块根(source_module 标记; 该标记条目允许匿名下载)
AVATAR_MODULE_KEY = "avatar"
AVATAR_MODULE_LABEL = "用户头像"

# 允许上传的图片扩展名(不含点)
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"}


class AvatarService:
    """用户头像服务

    注入统一文件服务(FileService), 头像等用户相关文件统一存于虚拟目录
    /用户头像/<用户ID>/ 下(source_module='avatar', 文件管理可见但只读,
    下载走 /file/filesystem/download/{entry_id} 且允许匿名访问)。
    """

    def __init__(
        self,
        file_service: FileService | None = None,
        user_dao: UserDao | None = None,
    ):
        """依赖注入构造器: 统一文件服务 + 用户DAO"""
        self.file_service = file_service or FileService()
        self.user_dao = user_dao or UserDao()

    @staticmethod
    def _extract_entry_id(avatar: str | None) -> str | None:
        """从历史头像字段解析文件条目ID(仅识别本服务写入的下载路径/裸条目ID格式)"""
        if not avatar:
            return None
        matched = re.search(r"/file/filesystem/download/([0-9a-f]{32})$", avatar)
        if matched:
            return matched.group(1)
        if re.fullmatch(r"[0-9a-f]{32}", avatar):
            return avatar
        return None

    async def upload_avatar(self, user_id: str, file: UploadFile) -> dict:
        """
        上传用户头像: 经统一文件服务存入 /用户头像/<用户ID>/ 并回写用户头像字段
        :param user_id: 当前登录用户ID
        :param file: 图片文件
        :return: {"avatar": 下载路径, "entry_id": 文件条目ID}
        :raises ValueError: 格式不允许
        """
        filename = file.filename or "avatar.png"
        self._validate_filename(filename)
        folder = await self._ensure_folder(user_id)
        # 上传新头像(内容哈希去重, 内容引用计数由文件条目维护)
        entry = await self.file_service.upload_file(
            file, "用户头像", folder.id, owner_user_id=user_id
        )
        return await self._apply_avatar(user_id, entry)

    async def init_upload(
        self, user_id: str, req: MultipartInitRequest
    ) -> MultipartInitResponse:
        """初始化头像预签名上传(同名自动加序号, 返回服务端确认的落库名)

        :param user_id: 当前登录用户ID
        :param req: 初始化请求(文件名/大小/SHA-256)
        :return: 会话凭证与预签名URL(含最终落库文件名)
        """
        original = req.filename or "avatar.png"
        self._validate_filename(original)
        folder = await self._ensure_folder(user_id)
        for index in range(20):
            req.filename = (
                original if index == 0 else self._numbered_name(original, index + 1)
            )
            req.pid = folder.id
            try:
                response = await self.file_service.init_multipart_upload(
                    req, owner_user_id=user_id
                )
            except ConflictError:
                continue
            response.filename = req.filename
            return response
        raise ConflictError(f"头像同名文件过多: {original}")

    async def complete_upload(
        self, user_id: str, upload_id: str, req: MultipartCompleteRequest
    ) -> dict:
        """完成头像上传: 合并分片/建条目后回写用户头像并清理旧头像

        :param user_id: 当前登录用户ID
        :param upload_id: 分片会话凭证
        :param req: 完成请求(文件名/分片清单)
        :return: {"avatar": 下载路径, "entry_id": 文件条目ID}
        """
        original = req.filename or "avatar.png"
        self._validate_filename(original)
        folder = await self._ensure_folder(user_id)
        for index in range(20):
            req.filename = (
                original if index == 0 else self._numbered_name(original, index + 1)
            )
            req.pid = folder.id
            try:
                entry = await self.file_service.complete_multipart_upload(
                    upload_id, req, owner_user_id=user_id
                )
            except ConflictError:
                continue
            return await self._apply_avatar(user_id, entry)
        raise ConflictError(f"头像同名文件过多: {original}")

    async def register_existing(self, user_id: str, req: EntryCreateRequest) -> dict:
        """头像秒传登记: 内容已存在时直接建条目并回写用户头像

        :param user_id: 当前登录用户ID
        :param req: 条目创建请求(文件名/内容SHA-256/大小)
        :return: {"avatar": 下载路径, "entry_id": 文件条目ID}
        """
        original = req.name or "avatar.png"
        self._validate_filename(original)
        folder = await self._ensure_folder(user_id)
        for index in range(20):
            req.name = (
                original if index == 0 else self._numbered_name(original, index + 1)
            )
            req.pid = folder.id
            try:
                entry = await self.file_service.create_entry(
                    req, owner_user_id=user_id
                )
            except ConflictError:
                continue
            return await self._apply_avatar(user_id, entry)
        raise ConflictError(f"头像同名文件过多: {original}")

    @staticmethod
    def _validate_filename(filename: str) -> None:
        """校验头像扩展名(仅允许常见图片格式)"""
        ext = Path(filename).suffix.lstrip(".").lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            raise ValueError(
                f"不支持的图片格式 '{ext}', 允许: {'/'.join(sorted(ALLOWED_IMAGE_EXTS))}"
            )

    @staticmethod
    def _numbered_name(filename: str, number: int) -> str:
        """同名文件加序号: avatar.png → avatar (2).png"""
        stem, ext = Path(filename).stem, Path(filename).suffix
        return f"{stem} ({number}){ext}"

    async def _ensure_folder(self, user_id: str) -> FileEntry:
        """确保头像模块根目录与用户专属子目录存在"""
        root = await self.file_service.ensure_module_root(
            AVATAR_MODULE_KEY, AVATAR_MODULE_LABEL, user_id
        )
        return await self.file_service.ensure_folder(user_id, root.id, user_id)

    async def _apply_avatar(self, user_id: str, entry: FileEntry) -> dict:
        """回写用户头像字段并清理旧头像条目"""
        user = await self.user_dao.get(user_id)
        old_entry_id = self._extract_entry_id(user.avatar if user else None)
        if old_entry_id and old_entry_id != entry.id:
            try:
                old_entry = await self.file_service.get_file_entry(old_entry_id)
                if old_entry and old_entry.source_module == AVATAR_MODULE_KEY:
                    await self.file_service.delete_file(old_entry_id)
            except Exception as e:
                logger.warning(f"清理旧头像条目失败 {old_entry_id}: {e}")

        # 头像字段存 API 下载路径(匿名可访问, 前端 <img> 直接可用)
        avatar_url = f"/base_server/file/filesystem/download/{entry.id}"
        await self.user_dao.update(user_id, UserUpdate(avatar=avatar_url))
        return {"avatar": avatar_url, "entry_id": entry.id}

    async def delete_avatar(self, user_id: str) -> None:
        """
        删除当前头像还原默认(用户名首字头像): 清理 avatar 模块条目并置空用户头像字段
        :param user_id: 当前登录用户ID
        :raises ValueError: 当前无上传头像(字段为空)
        """
        user = await self.user_dao.get(user_id)
        if not user or not user.avatar:
            raise ValueError("当前未设置头像")
        # 清理 avatar 模块的头像文件条目(仅识别本服务写入的格式, 外部链接不动)
        entry_id = self._extract_entry_id(user.avatar)
        if entry_id:
            entry = await self.file_service.get_file_entry(entry_id)
            if entry and entry.source_module == AVATAR_MODULE_KEY:
                try:
                    await self.file_service.delete_file(entry_id)
                except Exception as e:
                    logger.warning(f"清理头像条目失败 {entry_id}: {e}")
        # 置空头像字段, 前端回退为用户名首字默认头像
        await self.user_dao.update(user_id, UserUpdate(avatar=None))
