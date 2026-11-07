# module_file 网络文件系统模块

虚拟文件树 + S3 兼容对象存储（rustfs/MinIO 等），对所有调用方（前端 / 其他后端模块）暴露**完全一致**的接口。

## 1. 架构

```
前端(Vue3) / 其他模块(FileService)
        │  统一 REST 接口 (/file/filesystem/*)
        ▼
controller/filesystem.py ──► service/filesystem.py (FileService)
        │                          │
        │                          ├── dao/file_entry_dao.py    虚拟文件树(条目: 文件+目录, pid树, 逻辑路径)
        │                          ├── dao/file_content_dao.py  物理内容(内容哈希去重, 引用计数)
        │                          ▼
        │                  StorageInterface(存储抽象)
        │                          └── storage_s3.py     S3协议(rustfs/MinIO/oss, aioboto3)
        ▼
config/filesystem.py: 启动时按动态配置(file_system 组)构建全局存储单例
```

- **虚拟树与物理存储解耦**：`file_entry` 表记录文件/目录树（pid + logical_path），`file_content` 表记录物理内容（content_hash 主键、physical_storage 物理键、storage_type 来源、ref_count 引用计数）。
- **内容哈希去重**：同一内容全系统仅存一份，复制/秒传零成本；引用计数归零自动清理物理文件。
- **存储无关**：业务层只见 `StorageInterface`（save/load/iter_chunks/delete/exists/size/list + 分片上传五件套），更换 S3 端点不改业务代码。

## 2. 存储语义

bucket 为根目录，物理键即 bucket 内 object key。

`config.dev.yaml`（首启种子，之后以 系统管理→通用配置页 的 `file_system` 组为准）：

```yaml
file_system:
  max_size: 10                # 直传单文件上限(MB),超过自动走分片上传
  allowed_extensions:         # MIME 白名单(支持 image/* 通配),空=不限制
    - "application/pdf"
    - "image/*"
  # s3 / rustfs / minio 共用以下 S3 协议配置
  endpoint_url: "http://127.0.0.1:20004"
  access_key: "minioadmin"
  secret_key: "minioadmin"
  bucket: "codebiu-base"      # 项目专用桶(启动时不存在自动创建; 桶名需符合 S3 规范, 无下划线)
  region: "us-east-1"
  secure: false
```

- **前端对接**：上传先探 `GET /upload-mode`（返回 `direct` 预签名直传），下载统一走 `GET /download/{entry_id}`（302 预签名直链）。
- 换桶/换端点：自行搬运桶内对象 → 通用配置页更新连接信息 → 重启。

## 3. REST 接口（前后端协议，与存储类型无关）

挂载前缀 `/file/filesystem`，权限码 `main:file:read/create/update/delete`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/upload` | 小文件直传（multipart 表单，哈希去重秒传） |
| POST | `/multipart/init` | 初始化分片上传（返回会话凭证；内容已存在时 `is_existing=true` 秒传） |
| PUT | `/multipart/{upload_id}/parts/{part_number}` | 上传单个分片（body 为二进制，最后一片可小于标准分片） |
| GET | `/multipart/{upload_id}/parts` | 查询已上传分片（断点续传） |
| POST | `/multipart/{upload_id}/complete` | 完成上传（合并分片、SHA-256 校验、按真实哈希归位、建条目） |
| DELETE | `/multipart/{upload_id}` | 取消分片上传并清理已传分片 |
| POST | `/upload-complete` | 秒传建条目（init 返回 `is_existing=true` 后调用） |
| POST | `/folder?name=&pid=` | 创建目录 |
| POST | `/mkdir-p?path=/a/b/c` | 按路径递归创建目录（mkdir -p） |
| GET | `/list-dir?pid=&name=&page=&size=` | 按 pid 浏览目录（目录排前） |
| GET | `/list-by-path?path=/a/b` | 按逻辑路径浏览目录 |
| GET | `/path?path=/a/b/readme.md` | 按逻辑路径查询条目元数据 |
| GET | `/search?keyword=&page=&size=` | 全树模糊搜索（名称/路径） |
| GET | `/dirs?pid=` | 子目录列表（目录树懒加载） |
| GET | `/entries/{id}` | 条目元数据 |
| PUT | `/entries/{id}` | 更新描述/名称 |
| PUT | `/entries/{id}/rename?new_name=` | 重命名（目录同步子树路径） |
| PUT | `/entries/{id}/move?target_pid=` | 移动（环形防护） |
| POST | `/copy?entry_id=&target_pid=` | 复制（文件共享内容，目录递归整树） |
| GET | `/download/{id}` | 流式下载（后端代理） |
| DELETE | `/files/{id}` | 删除文件（引用计数-1，归零清物理） |
| DELETE | `/folders/{id}` | 递归删除目录 |
| GET | `/stats` | 统计（条目/内容/占用/当前存储类型） |

### 分片上传协议（大文件 >10MB 前端自动分流）

1. **计算哈希**：前端用 `crypto.subtle` 计算 SHA-256。
2. **初始化**：`POST /multipart/init`（filename/file_size_bytes/content_hash）→ 返回 `upload_id`（HMAC 签名会话凭证，自包含物理键与存储会话ID，24h 有效）与 `part_size`（8MB）。内容已存在返回 `is_existing=true`，跳到第 4 步秒传。
3. **上传分片**：按 `part_size` 切片，逐片 `PUT /multipart/{upload_id}/parts/{n}`（body 为二进制），保存响应 `etag`。
4. **完成**：`POST /multipart/{upload_id}/complete`（filename/pid/parts 列表）→ 合并分片、流式计算真实 SHA-256、按哈希归位物理文件（同内容去重）、创建虚拟条目。秒传场景改调 `POST /upload-complete`。
5. **中断恢复**：`GET /multipart/{upload_id}/parts` 查询已传分片后续传；`DELETE /multipart/{upload_id}` 取消并清理。

> 分片上传走 S3 原生 Multipart Upload（预签名 URL 直传，数据面不经过服务端）。

## 4. 其他模块如何操作文件

跨模块仅依赖 `FileService`（或 DI 工厂），不要直接操作 module_file 的 dao/do 内部结构。

```python
from module_file.service.filesystem import FileService

service = FileService()

# —— 增 ——
entry = await service.upload_file(upload_file, description, pid)       # HTTP multipart 直传
entry = await service._upload_content(data_bytes, "report.pdf", pid=pid)  # 字节内容直传(≤max_size)
entry = await service.create_entry(EntryCreateRequest(...))            # 秒传建条目
folder = await service.mkdir_p("/rag/exports")                         # mkdir -p

# —— 删 ——
await service.delete_file(entry.id)      # 文件
await service.delete_folder(folder.id)   # 目录(递归)

# —— 改 ——
await service.rename(entry.id, "v2.pdf")
await service.move(entry.id, target_pid)
await service.copy_entry(entry.id, target_pid)  # 内容哈希去重,零物理复制

# —— 查 ——
entry = await service.get_file_entry(entry_id)
entry = await service.get_by_path("/rag/docs/report.pdf")
page = await service.list_by_pid(pid, PaginationParams(page=1, size=100))
page = await service.search("report", PaginationParams(page=1, size=50))
data: bytes = await service.read_file_bytes(entry.id)
text: str = await service.read_file_text(entry.id)
async for chunk in service.stream_entry_chunks(entry.id):  # 大文件流式
    ...
stats = await service.get_stats()  # 占用统计

# —— 底层直连(不建虚拟条目,仅临时文件场景) ——
await service.storage.save("tmp/x.bin", b"...")
data = await service.storage.load("tmp/x.bin")
```

### FastAPI 依赖注入（在自定义 controller 中）

```python
from module_file.dependencies.filesystem import get_file_service

@router.post("/attach")
async def attach(
    service: FileService = Depends(get_file_service),
    current_user_id: str = Depends(get_current_user_id),
):
    entry = await service._upload_content(content, "a.txt", pid=None, owner_user_id=current_user_id)
```

### Celery 任务进程中

`FileService` 的 DAO 方法用 `@DaoRel` 自管事务，在 worker 的 `run_async` 协程里可直接 `await service.xxx(...)`。

## 5. 目录结构

```
module_file/
├── config/
│   ├── filesystem.py          全局存储单例(按动态配置 file_system 组)
│   ├── filetype.py            文件类型配置
│   └── server.py              /file 子应用挂载
├── controller/filesystem.py   REST 接口
├── dao/                       file_entry_dao / file_content_dao
├── dependencies/filesystem.py DI 工厂
├── do/filesystem.py           表模型+请求/响应模型
├── service/filesystem.py      业务逻辑(FileService,含分片上传)
└── utils/multi_storage/       存储抽象
    ├── storage_factory.py     工厂(实例化 S3 实现)
    ├── do/storage_config.py   StorageType(S3) + 配置类
    └── session/
        ├── interface/storage_interface.py   存储接口协议(含分片五件套)
        └── impl/storage_s3.py                S3协议实现(原生 Multipart Upload)
```
