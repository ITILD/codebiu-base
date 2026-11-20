# -*- coding: utf-8 -*-
"""module_office 文档解析接口契约测试(基线版: 仅 MinerU 外部服务, 五类版式文档)

覆盖: /office/document-parse/get-markdown-by-file 的参数校验与类型拦截契约
- 不支持的文件类型(.xyz 等非版式文档)应 400
- 缺少 file 表单字段应 422

说明:
- txt/md 等纯文本由 text-local 本地引擎直读解析(200 返回原文);
  .xyz 等无引擎匹配的类型仍 400 拒绝
- 真实解析路径(远程 mineru.net / 本地 docker)依赖外部服务与 token,
  单元/契约层不覆盖, 见 tests/module_office/service/test_document_parse.py
- app.py 主入口按设计挂载 /office 子应用; 测试内显式 import 触发路由注册
"""

import time
import uuid

import httpx

# 显式触发 /office 子应用挂载与控制器路由注册
import module_office.config.server  # noqa: F401
import module_office.controller.document_parse  # noqa: F401

PARSE_BASE = "/office/document-parse"


def _suffix() -> str:
    """生成时间戳+随机唯一后缀, 避免临时文件相互覆盖"""
    return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


async def test_get_markdown_by_file_unsupported_type(client: httpx.AsyncClient):
    """上传不支持的文件类型应 400(服务层 ValueError 映射)"""
    suffix = _suffix()
    resp = await client.post(
        f"{PARSE_BASE}/get-markdown-by-file",
        files={"file": (f"binary_{suffix}.xyz", b"\x00\x01not-a-doc", "application/octet-stream")},
    )
    assert resp.status_code == 400, resp.text
    assert "不支持的文件类型" in resp.json()["detail"], resp.text


async def test_get_markdown_by_file_plain_text_local(client: httpx.AsyncClient):
    """纯文本(.txt)由 text-local 引擎本地直读, 200 返回原文 markdown"""
    suffix = _suffix()
    resp = await client.post(
        f"{PARSE_BASE}/get-markdown-by-file",
        files={"file": (f"parse_in_{suffix}.txt", "纯文本本地直读解析".encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    assert "纯文本本地直读解析" in resp.text, resp.text


async def test_get_markdown_by_file_missing_file(client: httpx.AsyncClient):
    """缺少 file 表单字段应 422"""
    resp = await client.post(f"{PARSE_BASE}/get-markdown-by-file")
    assert resp.status_code == 422, resp.text
