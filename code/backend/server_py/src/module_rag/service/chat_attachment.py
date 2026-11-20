"""问答附件入库服务: 上传文件存入用户默认临时知识库并走知识库解析管线

临时知识库(temp 分类)按用户自动 get-or-create, 每用户至多一个
(部分唯一索引 uq_project_temp_kb 兜底并发); 文档经统一存储登记为
project_document, 解析/分块/向量化与知识库文档同链路, 检索侧由
RagChatService 自动并入本轮检索范围。
"""

import logging
import os

from sqlalchemy.exc import IntegrityError

from common.utils.fastapi_ex.exceptions import ConflictError
from module_file.do.filesystem import (
    EntryCreateRequest,
    MultipartCompleteRequest,
    MultipartInitRequest,
    MultipartInitResponse,
    UploadModeResponse,
)
from module_rag.do.project import KbCategory, Project, ProjectCreate
from module_rag.dao.project import ProjectDao
from module_rag.service.project import ProjectService
from module_rag.service.project_document import (
    ProjectDocumentService,
)
from module_rag.do.project_document import ProjectDocument

logger = logging.getLogger(__name__)

# 临时知识库固定命名(用户可在知识库页改名; 唯一性靠分类而非名称)
TEMP_KB_NAME = "个人问答知识库"
TEMP_KB_DESCRIPTION = "问答附件自动入库的个人知识库(会话上传文件在此归纳, 供问答检索)"


async def get_temp_kb(user_id: str) -> Project | None:
    """查询用户临时知识库(模块级便捷函数, 检索范围注入等轻量场景直接复用)

    :param user_id: 用户ID
    :return: 临时知识库(未创建返回 None, 不自动创建)
    """
    return await ProjectDao().get_temp_kb(user_id)


class ChatAttachmentService:
    """问答附件服务(上传 → 临时库登记 → 解析任务派发由控制器复用)"""

    def __init__(self, project_service: ProjectService, document_service: ProjectDocumentService):
        """依赖注入构造器(经 FastAPI 依赖工厂装配, 见 controller/rag_chat.py)"""
        self.project_service = project_service
        self.project_dao = project_service.project_dao
        self.document_service = document_service

    async def get_kb(self, user_id: str) -> Project | None:
        """查询用户临时知识库(未创建返回 None, 不自动创建)"""
        return await self.project_dao.get_temp_kb(user_id)

    async def ensure_temp_kb(self, user_id: str) -> Project:
        """获取或创建用户临时知识库(并发创建由唯一索引兜底, 冲突后重查)"""
        project = await self.get_kb(user_id)
        if project:
            return project
        try:
            project_id = await self.project_service.add(
                ProjectCreate(
                    name=TEMP_KB_NAME,
                    description=TEMP_KB_DESCRIPTION,
                    is_private=True,
                    kb_category=KbCategory.TEMP.value,
                ),
                user_id,
            )
            logger.info(f"用户 {user_id} 临时知识库已创建: {project_id}")
        except IntegrityError:
            # 并发上传同时建库: 唯一索引拒绝后来者, 重查先建的那一个
            logger.info(f"用户 {user_id} 临时知识库并发创建冲突, 复用已建库")
        project = await self.get_kb(user_id)
        if not project:
            raise RuntimeError("临时知识库创建失败")
        return project

    async def upload(self, file, user_id: str) -> ProjectDocument:
        """上传问答附件: 登记到用户临时知识库(解析任务由调用方派发)

        临时库为同一虚拟目录, 同名附件(如不同会话再次上传同名文件)自动加序号
        重命名, 不打断用户流程; 内容层面的去重由统一存储的哈希秒传兜底

        :param file: 上传文件对象(UploadFile)
        :param user_id: 当前用户ID
        :return: 登记的文档记录(parse_status=pending, 待解析任务接管)
        """
        project = await self.ensure_temp_kb(user_id)
        original = file.filename or "附件"
        for index in range(20):
            try:
                return await self.document_service.upload_document(
                    project.id, file, user_id
                )
            except ConflictError:
                # 同名冲突: 改写文件名后重试(游标回零, 避免二次读到空内容)
                await file.seek(0)
                file.filename = self._numbered_name(original, index + 2)
        raise ConflictError(f"临时知识库同名附件过多: {original}")

    def get_upload_mode(self) -> UploadModeResponse:
        """查询上传模式(direct=预签名直传 / proxy=服务端中转)"""
        return self.document_service.file_service.get_upload_mode()

    async def init_multipart(
        self, req: MultipartInitRequest, user_id: str
    ) -> MultipartInitResponse:
        """初始化预签名上传会话(落库到用户临时知识库, 同名自动加序号)

        重名判断在凭证签发阶段完成, 冲突时改写文件名重试(不消耗数据面流量);
        最终落库名经响应 filename 返回, 前端 complete/秒传阶段沿用。

        :param req: 初始化请求(文件名/大小/SHA-256)
        :param user_id: 当前用户ID
        :return: 会话凭证与预签名URL(is_existing=True 时直接走秒传登记)
        """
        project = await self.ensure_temp_kb(user_id)
        original = req.filename or "附件"
        for index in range(20):
            req.filename = original if index == 0 else self._numbered_name(original, index + 1)
            try:
                response = await self.document_service.init_multipart_upload(
                    project.id, req, owner_user_id=user_id
                )
            except ConflictError:
                continue
            response.filename = req.filename
            return response
        raise ConflictError(f"临时知识库同名附件过多: {original}")

    async def complete_multipart(
        self,
        upload_id: str,
        req: MultipartCompleteRequest,
        user_id: str,
    ) -> ProjectDocument:
        """完成预签名上传并登记文档(同名冲突自动加序号后重试合并)

        冲突校验发生在分片合并之前, 重试不会产生副作用。

        :param upload_id: 分片会话凭证
        :param req: 完成请求(文件名/分片清单)
        :param user_id: 当前用户ID
        :return: 登记的文档记录
        """
        project = await self.ensure_temp_kb(user_id)
        original = req.filename or "附件"
        for index in range(20):
            req.filename = original if index == 0 else self._numbered_name(original, index + 1)
            try:
                return await self.document_service.complete_multipart_upload(
                    project.id, upload_id, req, user_id
                )
            except ConflictError:
                continue
        raise ConflictError(f"临时知识库同名附件过多: {original}")

    async def create_from_content(
        self, req: EntryCreateRequest, user_id: str
    ) -> ProjectDocument:
        """秒传登记(内容已存在时直接建条目, 同名冲突自动加序号)

        :param req: 条目创建请求(文件名/内容SHA-256/大小)
        :param user_id: 当前用户ID
        :return: 登记的文档记录
        """
        project = await self.ensure_temp_kb(user_id)
        original = req.name or "附件"
        for index in range(20):
            req.name = original if index == 0 else self._numbered_name(original, index + 1)
            try:
                return await self.document_service.create_document_from_content(
                    project.id, req, user_id
                )
            except ConflictError:
                continue
        raise ConflictError(f"临时知识库同名附件过多: {original}")

    @staticmethod
    def _numbered_name(filename: str, number: int) -> str:
        """同名文件加序号: 报告.pdf → 报告 (2).pdf"""
        stem, ext = os.path.splitext(filename)
        return f"{stem} ({number}){ext}"
