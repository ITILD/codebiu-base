"""知识库模块 子应用装配: 路由挂载与模块级初始化"""

from common.config.server import app
from common.utils.fastapi_ex.exceptions import BizFastAPI
import logging
from sqlalchemy import inspect, text

from common.config.db import db_manager
from common.config.lifespan import register_init_hook
# 导入即注册本模块权限声明到权限中心(rag 域)
from module_rag.config import permissions as rag_permissions  # noqa: F401
# 导入即注册本模块字典种子到字典中心(rag 域,与代码枚举对齐)
from module_rag.config import dict_seed as rag_dict_seed  # noqa: F401
# 注册 rag 业务条目下载授权钩子(文件管理页下载 /rag/<项目>/ 子树条目时
# 按项目 editor 及以上档位放行, 判定逻辑见 dependencies/permission.py)
from module_file.config.download_grant import register_download_grant
from module_rag.dependencies.permission import check_entry_download_grant
from module_rag.do.project_document import DocType

register_download_grant("rag", check_entry_download_grant)

logger = logging.getLogger(__name__)

module_app = BizFastAPI()

app.mount("/rag", module_app)

logger.debug("module_rag服务配置完成")


@register_init_hook
async def ensure_project_document_parse_steps():
    """存量表补列: project_document.parse_steps(入库步骤进度 JSONB, 幂等;
    create_all 不为旧表加列)"""
    if db_manager.db_rel is None:
        return
    engine = db_manager.db_rel.engine
    async with engine.begin() as conn:
        cols = await conn.run_sync(
            lambda sc: {c["name"] for c in inspect(sc).get_columns("project_document")}
        )
        if "parse_steps" not in cols:
            await conn.execute(
                text("ALTER TABLE project_document "
                     "ADD COLUMN parse_steps JSONB NOT NULL DEFAULT '{}'")
            )
            logger.info("project_document.parse_steps 步骤进度列已补齐")
        # content_hash: 统一存储口径关联列(旧数据 NULL 走本地路径, 幂等补列)
        if "content_hash" not in cols:
            await conn.execute(
                text("ALTER TABLE project_document "
                     "ADD COLUMN content_hash VARCHAR(64) DEFAULT NULL")
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_project_document_content_hash "
                     "ON project_document (content_hash)")
            )
            logger.info("project_document.content_hash 内容哈希列已补齐")
        # entry_id: 条目级口径关联列(文档位于虚拟目录 /rag/<项目名>/ 下, 旧数据 NULL)
        if "entry_id" not in cols:
            await conn.execute(
                text("ALTER TABLE project_document "
                     "ADD COLUMN entry_id VARCHAR(50) DEFAULT NULL")
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_project_document_entry_id "
                     "ON project_document (entry_id)")
            )
            logger.info("project_document.entry_id 条目关联列已补齐")
        # project.root_entry_id: 项目根文件夹条目ID(惰性补建, 旧项目 NULL)
        pcols = await conn.run_sync(
            lambda sc: {c["name"] for c in inspect(sc).get_columns("project")}
        )
        if "root_entry_id" not in pcols:
            await conn.execute(
                text("ALTER TABLE project "
                     "ADD COLUMN root_entry_id VARCHAR(50) DEFAULT NULL")
            )
            logger.info("project.root_entry_id 项目根目录列已补齐")


@register_init_hook
async def ensure_project_temp_kb_unique_index():
    """临时知识库唯一性: 每用户至多一个 temp 分类知识库(问答附件入库自动创建,
    并发上传靠部分唯一索引兜底, 幂等)"""
    if db_manager.db_rel is None:
        return
    engine = db_manager.db_rel.engine
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_project_temp_kb "
                 "ON project (created_by) WHERE kb_category = 'temp'")
        )


@register_init_hook
async def ensure_file_whitelist_covers_doc_types():
    """文件存储 MIME 白名单补齐知识库文档类型(幂等)

    问答附件与知识库上传共用统一文件存储, 其 MIME 白名单(file_system 组,
    管理页可改)早于 DocType 扩充配置时缺 ppt/纯文本等类型 → 知识库合法类型
    上传被拒; 白名单非空(空=不限制)时按 DocType.ALLOWED_EXTENSIONS 推导
    MIME 并补缺, 不动管理员配置的其他条目
    """
    import mimetypes

    from common.config.dynamic import get_settings
    from common.config.dynamic.schemas import FileSystemSettings
    from common.config.dynamic.service import settings_service

    fs = await get_settings(FileSystemSettings)
    allowed = [a.lower() for a in (fs.allowed_extensions or [])]
    if not allowed:  # 空列表 = 不限制
        return
    allowed_set = set(allowed)

    def _covered(mime: str) -> bool:
        return mime in allowed_set or f"{mime.split('/')[0]}/*" in allowed_set

    required: set[str] = set()
    for ext in DocType.ALLOWED_EXTENSIONS:
        mime, _ = mimetypes.guess_type(f"probe.{ext}")
        required.add(mime or "application/octet-stream")
    required.add("application/octet-stream")  # .log 等未登记扩展名的兜底 MIME
    missing = sorted(m for m in required if not _covered(m))
    if not missing:
        return
    await settings_service.update(
        "file_system",
        {"allowed_extensions": [*fs.allowed_extensions, *missing]},
        updated_by="seed:rag-doc-whitelist",
    )
    # 同步刷新本进程已装配的存储配置(白名单即时生效, 无需重启)
    import module_file.config.filesystem as fs_conf_mod
    from module_file.utils.multi_storage.do.storage_config import StorageConfigFactory

    fs_conf_mod.storage_config = StorageConfigFactory.create(
        "s3", (await get_settings(FileSystemSettings)).model_dump()
    )
    logger.info(f"文件存储 MIME 白名单已补齐知识库文档类型: {missing}")


@register_init_hook
async def ensure_user_model_fallback_column():
    """存量表补列: user_model.fallback_disabled(用户级回退开关, v4 4.3 兜底链可关闭; 幂等)"""
    if db_manager.db_rel is None:
        return
    engine = db_manager.db_rel.engine
    async with engine.begin() as conn:
        cols = await conn.run_sync(
            lambda sc: {c["name"] for c in inspect(sc).get_columns("user_model")}
        )
        if "fallback_disabled" not in cols:
            await conn.execute(
                text("ALTER TABLE user_model "
                     "ADD COLUMN fallback_disabled BOOLEAN NOT NULL DEFAULT FALSE")
            )
            logger.info("user_model.fallback_disabled 回退开关列已补齐")


@register_init_hook
async def ensure_user_model_voice_columns():
    """存量表补列: user_model 语音小模型绑定 4 列(asr/tts/vad/denoise, 幂等;
    create_all 不为旧表加列)"""
    if db_manager.db_rel is None:
        return
    engine = db_manager.db_rel.engine
    async with engine.begin() as conn:
        cols = await conn.run_sync(
            lambda sc: {c["name"] for c in inspect(sc).get_columns("user_model")}
        )
        for col in ("asr_model_id", "tts_model_id", "vad_model_id", "denoise_model_id"):
            if col not in cols:
                await conn.execute(
                    text(f"ALTER TABLE user_model ADD COLUMN {col} VARCHAR(50) DEFAULT NULL")
                )
                logger.info(f"user_model.{col} 语音模型绑定列已补齐")
