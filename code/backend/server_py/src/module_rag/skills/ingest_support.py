"""知识库入库链路的展开项输入准备器(REQ-018, kb_ingest_agent parse 步骤挂载)

职责: 在 job 执行侧(inline/worker 同进程)把展开项的 document_id 物化为
{file_path, filename, size_hint} —— 临时文件生命周期与 job 一致(结束统一清理),
避免跨进程传递临时路径。物化逻辑与既有 parse_document 的内容定位一致(content_hash
→ locate → stream 落盘)。
"""

import logging
import tempfile
from pathlib import Path

from module_agent.service.skill_runtime import SkillContext

logger = logging.getLogger(__name__)


async def resolve_document_input(item: dict, ctx: SkillContext) -> dict:
    """展开项输入准备器: document_id → 文件物化字段

    :param item: 展开项(至少含 document_id)
    :param ctx: job 执行上下文(用户身份)
    :return: {file_path, filename, size_hint, __cleanup_paths}; 文档不存在抛 ValueError
    """
    from module_rag.dao.project_document import ProjectDocumentDao
    from module_file.service.filesystem import FileService

    document_id = str(item.get("document_id") or "")
    document = await ProjectDocumentDao().get(document_id)
    if document is None:
        raise ValueError(f"文档不存在: {document_id}")

    content_hash: str | None = document.content_hash or None
    file_path: Path | None = None
    temp_dir_path: str | None = None
    if document.entry_id:
        file_service = FileService()
        # mkdtemp 而非 TemporaryDirectory: 后者对象离开作用域即删目录,
        # 而本函数返回后 skill 才读取文件; 生命周期由 job 结束统一清理
        temp_dir_path = tempfile.mkdtemp(prefix="kb_ingest_")
        file_path = Path(temp_dir_path) / (document.name or "document")
        with file_path.open("wb") as f:
            async for chunk in file_service.stream_entry_chunks(document.entry_id):
                f.write(chunk)
    if file_path is None:
        raise ValueError(
            f"文档内容不可定位(entry_id 缺失, content_hash={content_hash}): {document_id}"
        )

    return {
        "file_path": str(file_path),
        "filename": document.name or file_path.name,
        "size_hint": int(document.file_size_bytes or file_path.stat().st_size),
        # job 结束统一清理临时目录(AgentJobService._cleanup_paths)
        "__cleanup_paths": [temp_dir_path],
    }
