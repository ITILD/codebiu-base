# 项目依赖管理表

### Python 依赖安装

```bash
# 安装所有 Python 依赖
uv sync
```

## Python 后端生产依赖

运行时必需的库,会打包到最终产品中,影响应用功能

以下是补全后的依赖表格，包含各依赖库的具体用途描述：

| 依赖名称      | 版本     | 类型 | 功能描述               | 用途                                                   | 安装命令           | 引入方式                         |
| ------------- | -------- | ---- | ---------------------- | ------------------------------------------------------ | ------------------ | -------------------------------- |
| **fastapi**   | ≥0.116.1 | 生产 | 高性能 Web 框架        | 构建 API 接口、微服务、后端应用                        | `uv add fastapi`   | `from fastapi import FastAPI`    |
| **pydantic**  | ≥2.11.7  | 生产 | 数据验证和设置管理     | 请求/响应数据验证、配置模型定义、类型注解              | `uv add pydantic`  | `from pydantic import BaseModel` |
| **sqlmodel**  | ≥0.0.24  | 生产 | SQL 数据库 ORM         | 数据库操作、结合 SQLAlchemy 和 Pydantic 的 ORM 工具    | `uv add sqlmodel`  | `from sqlmodel import SQLModel`  |
| **uvicorn**   | ≥0.35.0  | 生产 | ASGI 服务器            | 运行 FastAPI 应用的服务器、支持 HTTP/WebSocket         | `uv add uvicorn`   | `import uvicorn`                 |
| **dynaconf**  | ≥3.2.11  | 生产 | 配置管理               | 多环境配置管理（开发/测试/生产）、敏感信息分离         | `uv add dynaconf`  | `from dynaconf import settings`  |
| **psutil**    | ≥7.0.0   | 生产 | 系统监控               | 监控 CPU/内存/磁盘/网络使用情况、进程管理              | `uv add psutil`    | `import psutil`                  |
| **aiohttp**   | ≥3.12.15 | 生产 | HTTP 客户端/服务端     | 异步 HTTP 请求、爬虫开发、微服务通信、WebSocket 客户端 | `uv add aiohttp`   | `import aiohttp`                 |
| **requests**  | ≥2.32.5  | 生产 | HTTP 客户端            | 同步 HTTP 请求、API 调用、爬虫开发                     | `uv add requests`  | `import requests`                |
| **numpy**     | ≥2.3.2   | 生产 | 矩阵计算库             | 数值计算、科学计算、数据分析、机器学习                 | `uv add numpy`     | `import numpy`                   |
| **aiosqlite** | ≥0.21.0  | 生产 | 异步 SQLite 数据库     | 异步操作 SQLite 数据库                                 | `uv add aiosqlite` | `import aiosqlite`               |
| **asyncpg**   | ≥0.30.0  | 生产 | 异步 PostgreSQL 数据库 | 异步操作 PostgreSQL 数据库                             | `uv add asyncpg`   | `import asyncpg`                 |
| **python-multipart** | ≥0.0.20 | 生产 | 处理 multipart/form-data | 处理文件上传、表单数据解析                             | `uv add python-multipart` | `import multipart`               |
| **websockets** | ≥15.0.1  | 生产 | WebSocket 客户端/服务端 | WebSocket 通信、实时应用、聊天室、在线游戏              | `uv add websockets` | `import websockets`              |
| **aiofiles** | ≥25.1.0 | 生产 | 异步文件操作 | 异步读写文件，提高文件操作性能 | `uv add aiofiles` | `import aiofiles` |
| **casbin** | ≥1.43.0 | 生产 | 权限管理框架 | 支持 ACL、RBAC、ABAC 等多种访问控制模型 | `uv add casbin` | `import casbin` |
| **casbin-async-sqlalchemy-adapter** | ≥1.13.0 | 生产 | Casbin SQLAlchemy 适配器 | 为 Casbin 提供 SQLAlchemy 数据库适配器支持 | `uv add casbin-async-sqlalchemy-adapter` | `import casbin_async_sqlalchemy_adapter` |
| **fakeredis** | ≥2.32.1 | 生产 | Redis 模拟器 | 在测试环境中模拟 Redis 服务器 | `uv add fakeredis` | `import fakeredis` |
| **httpx** | ≥0.28.1 | 生产 | 异步 HTTP 客户端 | 支持异步和同步的 HTTP 客户端，功能比 requests 更丰富 | `uv add httpx` | `import httpx` |
| **pyjwt** | ≥2.10.1 | 生产 | JWT 处理库 | 生成和验证 JSON Web Tokens | `uv add pyjwt` | `import jwt` |
| **pwdlib** | ≥0.2.1 | 生产 | 密码哈希库 | 安全地哈希和验证密码，支持 Argon2 算法 | `uv add pwdlib[argon2]` | `import pwdlib` |
| **pyyaml** | ≥6.0.2 | 生产 | YAML 解析器 | 读写 YAML 格式的配置文件 | `uv add pyyaml` | `import yaml` |
| **opencv-contrib-python** | ≥4.11.0.86,<4.13 | 生产 | 计算机视觉库 | 图像处理、计算机视觉算法 | `uv add opencv-contrib-python` | `import cv2` |
| **pillow** | ≥11.3.0 | 生产 | 图像处理库 | 图像处理和操作 | `uv add pillow` | `from PIL import Image` |
| **beautifulsoup4** | ≥4.14.3 | 生产 | HTML/XML 解析器 | 解析和提取 HTML 或 XML 文档 | `uv add beautifulsoup4` | `from bs4 import BeautifulSoup` |
| **lxml** | ≥6.0.2 | 生产 | XML/HTML 处理器 | 高性能的 XML 和 HTML 处理库 | `uv add lxml` | `from lxml import etree` |
| **soundfile** | ≥0.13.1 | 生产 | 音频解码 | 在线 ASR/TTS 的音频解码与重采样 | `uv add soundfile` | `import soundfile` |
| **celery** | ≥5.6.1 | 生产 | 分布式任务队列 | 任务队列 celery 引擎(与 local 引擎双轨) | `uv add celery` | `import celery` |
| **langchain** | ≥1.2.15 | 生产 | LLM 应用框架 | LLM 编排基础框架 | `uv add langchain` | `import langchain` |
| **langchain-openai** | ≥1.1.0 | 生产 | LangChain OpenAI 集成 | LangChain 对 OpenAI API 的集成 | `uv add langchain-openai` | `from langchain_openai import ChatOpenAI` |
| **langchain-aws** | ≥1.1.0 | 生产 | LangChain AWS 集成 | LangChain 对 AWS 服务的集成 | `uv add langchain-aws` | `from langchain_aws import ChatBedrock` |
| **langchain-ollama** | ≥1.0.1 | 生产 | LangChain Ollama 集成 | LangChain 对 Ollama 本地服务的集成 | `uv add langchain-ollama` | `from langchain_ollama import ChatOllama` |
| **langchain-text-splitters** | ≥1.1.0 | 生产 | 文本切分 | 文档分块(ragflow 分块引擎) | `uv add langchain-text-splitters` | `import langchain_text_splitters` |
| **langgraph** | (随 langgraph-checkpoint-postgres) | 生产 | 状态机编排 | RAG 会话图编排 | `uv add langgraph` | `import langgraph` |
| **langgraph-checkpoint-postgres** | ≥3.1.2 | 生产 | 会话检查点 | RAG 会话状态持久化(postgres) | `uv add langgraph-checkpoint-postgres` | `import langgraph.checkpoint.postgres` |
| **psycopg** | ≥3.3.4 | 生产 | PostgreSQL 驱动 | 异步连接池(checkpointer) | `uv add psycopg[binary]` | `import psycopg` |
| **ag-ui-protocol** | ≥1.0.0 | 生产 | AG-UI 协议 | RAG 问答流式事件协议 | `uv add ag-ui-protocol` | `import ag_ui` |
| **aiosmtplib** | ≥5.1.2 | 生产 | SMTP 异步客户端 | 注册邮箱验证码发送 | `uv add aiosmtplib` | `import aiosmtplib` |
| **aioboto3** | ≥15.5.0 | 生产 | S3 异步客户端 | 文件存储 s3 类型 | `uv add aioboto3` | `import aioboto3` |
| **sse-starlette** | ≥3.3.2 | 生产 | SSE 流式响应 | Server-Sent Events 端点 | `uv add sse-starlette` | `import sse_starlette` |
| **lancedb** | ==0.30.0 | 生产 | 向量数据库 | 本地文件向量库(基线唯一向量后端) | `uv add lancedb` | `import lancedb` |
| **pyarrow** | ≥22.0.0 | 生产 | 列式数据结构 | lancedb 底层依赖 | `uv add pyarrow` | `import pyarrow` |
| **tiktoken** | ≥0.12.0 | 生产 | token 计数 | 轻量 token 计数(不依赖 transformers) | `uv add tiktoken` | `import tiktoken` |

## 后端开发依赖

仅开发阶段使用,可以不打包到最终产品中,影响应用功能(包括构建工具、测试工具、代码检查等)

| 依赖名称   | 版本   | 类型 | 功能描述        | 用途                                                           | 安装命令        | 引入方式        |
| ---------- | ------ | ---- | --------------- | -------------------------------------------------------------- | --------------- | --------------- |
| **pytest** | ≥9.0.2 | 测试 | Python 测试框架 | 单元测试/集成测试/功能测试、支持异步和参数化测试、生成测试报告 | `uv add pytest` | `import pytest` |
| **pytest-asyncio** | ≥1.1.0 | 测试 | 异步测试框架    | 支持 asyncio 的测试框架、异步测试用例、异步 fixture          | `uv add pytest-asyncio` | `import pytest_asyncio` |
