# -*- coding: utf-8 -*-
"""module_file 在线预览端点测试(REQ-016)
覆盖: 内联流式返回(内容一致/inline disposition) / 中文文件名 RFC 5987 编码 /
鉴权(匿名 401) / 条目不存在 404
"""
import os
from urllib.parse import quote

import pytest

BASE = "/file/filesystem"
UPLOAD_URL = f"{BASE}/upload"
PREVIEW_URL = f"{BASE}/preview/{{entry_id}}"
DELETE_FILE_URL = f"{BASE}/files/{{file_id}}"


async def _upload(client, filename: str, content: bytes, mime: str = "text/plain") -> str:
    """直传小文件并返回条目 ID"""
    resp = await client.post(UPLOAD_URL, files={"file": (filename, content, mime)})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_preview_inline_stream(client):
    """预览返回内联流: 内容一致 + inline disposition + 正确 MIME"""
    filename = f"preview_{os.urandom(4).hex()}.txt"
    content = f"preview content {os.urandom(8).hex()}".encode()
    entry_id = await _upload(client, filename, content)
    try:
        resp = await client.get(PREVIEW_URL.format(entry_id=entry_id))
        assert resp.status_code == 200, resp.text
        assert resp.content == content
        assert resp.headers["content-type"].startswith("text/plain")
        disposition = resp.headers["content-disposition"]
        assert disposition.startswith("inline"), disposition
        assert filename in disposition  # ASCII 回退文件名
    finally:
        await client.delete(DELETE_FILE_URL.format(file_id=entry_id))


@pytest.mark.asyncio
async def test_preview_chinese_filename_rfc5987(client):
    """中文文件名: disposition 携带 RFC 5987 编码段(UTF-8'' 前缀 + 百分号编码)"""
    filename = f"预览文档_{os.urandom(4).hex()}.md"
    content = "# 标题\n\n正文内容".encode("utf-8")
    entry_id = await _upload(client, filename, content, "text/markdown")
    try:
        resp = await client.get(PREVIEW_URL.format(entry_id=entry_id))
        assert resp.status_code == 200, resp.text
        disposition = resp.headers["content-disposition"]
        assert disposition.startswith("inline"), disposition
        assert "UTF-8''" in disposition, disposition
        assert quote(filename, safe="") in disposition
    finally:
        await client.delete(DELETE_FILE_URL.format(file_id=entry_id))


@pytest.mark.asyncio
async def test_preview_requires_login(client, anon_client):
    """匿名不可预览(401), 权限口径与下载一致(鉴权按条目判定, 条目需真实存在)"""
    filename = f"priv_{os.urandom(4).hex()}.txt"
    entry_id = await _upload(client, filename, b"private content")
    try:
        resp = await anon_client.get(PREVIEW_URL.format(entry_id=entry_id))
        assert resp.status_code == 401, resp.text
    finally:
        await client.delete(DELETE_FILE_URL.format(file_id=entry_id))


@pytest.mark.asyncio
async def test_preview_not_found(client):
    """不存在的条目 404"""
    resp = await client.get(PREVIEW_URL.format(entry_id="nonexistent-entry"))
    assert resp.status_code == 404, resp.text
