"""内置 static_func 纯函数(REQ-018): 对现实规则建模的固定规则函数

首批交付三个示例性规则能力(内容哈希/类型嗅探/正则抽取), 均为零 I/O 纯函数;
后续新增规则能力照此模式声明即可(不新增业务代码, 见设计 §2.6 判定树 Q1)。
"""

import hashlib
import re
from pathlib import PurePosixPath

from module_ai.functions import StaticFuncDef, register_static_func

# 常见扩展名 → MIME 映射(嗅探用, 精度足够技能层使用; 不做魔数级识别)
_MIME_BY_EXT: dict[str, str] = {
    ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown",
    ".pdf": "application/pdf", ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".csv": "text/csv", ".json": "application/json", ".xml": "application/xml",
    ".html": "text/html", ".zip": "application/zip", ".mp3": "audio/mpeg",
    ".mp4": "video/mp4", ".wav": "audio/wav",
}


def content_hash(data: bytes, algorithm: str = "sha256") -> str:
    """内容哈希(十六进制摘要): 同输入必同输出, 供幂等键/去重使用"""
    if algorithm not in ("sha256", "sha1", "md5"):
        raise ValueError(f"不支持的哈希算法: {algorithm}")
    return hashlib.new(algorithm, data).hexdigest()


def mime_detect(filename: str) -> str:
    """按扩展名嗅探 MIME 类型(未知扩展名回退 application/octet-stream)"""
    ext = PurePosixPath(filename.strip().lower()).suffix
    return _MIME_BY_EXT.get(ext, "application/octet-stream")


def regex_extract(text: str, pattern: str) -> list[str]:
    """正则抽取全部不重叠匹配(如邮箱/手机号/日期); 非法模式抛 re.error(permanent)"""
    return [m.group(0) for m in re.finditer(pattern, text)]


register_static_func(
    StaticFuncDef(
        key="content_hash",
        name="内容哈希",
        description="计算字节内容的 SHA-256/SHA-1/MD5 摘要(幂等键与去重基础能力)",
        func=content_hash,
    )
)
register_static_func(
    StaticFuncDef(
        key="mime_detect",
        name="文件类型嗅探",
        description="按文件扩展名识别 MIME 类型(未知回退 application/octet-stream)",
        func=mime_detect,
    )
)
register_static_func(
    StaticFuncDef(
        key="regex_extract",
        name="正则抽取",
        description="按正则模式从文本抽取全部匹配(邮箱/手机号/日期等结构化信息)",
        func=regex_extract,
    )
)
