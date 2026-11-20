"""纯文本本地解析器: txt/md/csv/log/json 直读, 不依赖任何外部解析服务。

定位: 纯文本类文件无需版式解析, 直接解码后按段落/标题切为 Chunk;
markdown 行内 ``#`` 标题识别为 TITLE(带级别), 其余按空行分段。
大段落在解析器内按字符上限粗切, 后续仍由分块策略统一重分块。
"""
import logging
import re
from pathlib import Path

from module_office.utils.file_parse.base import BaseParser
from module_office.utils.file_parse.do.chunk import Chunk, ContentType, Position

logger = logging.getLogger(__name__)

# 单 Chunk 字符上限(超出按上限粗切, 精细分块由下游分块策略负责)
_MAX_CHUNK_CHARS = 4000

# markdown ATX 标题: 1~6 个 # 开头
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


class TextParser(BaseParser):
    """纯文本本地解析器(utf-8 优先, gbk 兜底, 容错替换)"""

    async def extract(self, file: Path) -> list[Chunk]:
        """解码文件内容并按段落/标题切分为 Chunk 列表"""
        data = file.read_bytes()
        text = self._decode(data)
        return self._to_chunks(text)

    @staticmethod
    def _decode(data: bytes) -> str:
        """多编码解码: utf-8 优先, gbk 兜底, 最终容错替换"""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

    @staticmethod
    def _to_chunks(text: str) -> list[Chunk]:
        """按空行分段 + markdown 标题识别 + 超长粗切"""
        chunks: list[Chunk] = []
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            heading = _MD_HEADING.match(para.splitlines()[0])
            if heading and len(para.splitlines()) == 1:
                chunks.append(
                    Chunk(
                        content=heading.group(2).strip(),
                        content_type=ContentType.TITLE,
                        position=Position(page=1, heading_level=len(heading.group(1))),
                    )
                )
                continue
            for i in range(0, len(para), _MAX_CHUNK_CHARS):
                chunks.append(Chunk(content=para[i : i + _MAX_CHUNK_CHARS], position=Position(page=1)))
        return chunks
