"""Milvus 向量库实现(远程向量后端)

恢复自源项目并按基线规范改造:
- 纯稠密向量检索(COSINE), BM25/sparse/分词器混合检索逻辑已随基线口径移除
- pymilvus 延迟导入: 仅在真正连接/建表时才加载 SDK, 未启用 milvus 的部署零开销
- 过滤语法适配: 调用方按 SQL 风格书写谓词(如 project_id IN ('a','b')),
  实现内自动转为 Milvus 表达式(project_id in ['a','b']), 与 LanceDB 实现共用同一套调用代码
- create_all 自动发现: 遍历 VectorModel.registry, 仅创建远端尚未存在的集合(幂等)

连接失败: 启动时仅告警跳过(connect_all 内部容错), 其余模块不受影响。
"""

from __future__ import annotations

import asyncio
import logging
import re
from enum import Enum
from typing import TYPE_CHECKING, Any, get_args

from annotated_types import MaxLen
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from common.utils.db.do.db_config import MilvusConfig
from common.utils.db.orm.vector_model import VectorModel
from common.utils.db.session.interface.db_vector_interface import DBVectorInterface

if TYPE_CHECKING:
    from pymilvus import AsyncMilvusClient, CollectionSchema, DataType

logger = logging.getLogger(__name__)

# SQL 风格 IN 列表: "IN ('a','b')" (LanceDB SQL 语法)
_SQL_IN_RE = re.compile(r"\bIN\s*\(([^)]*)\)", re.IGNORECASE)

# 批量插入: 单 RPC 行数上限(行含 8KB 文本 + 1024 维向量, 500 行约 8MB, 防单请求体过大)
_INSERT_BATCH = 500
# 批量插入并发度(重叠网络往返; 服务端写入吞吐为主, 小并发即够)
_INSERT_CONCURRENCY = 4
# HNSW 索引: 图出度(写入速度/内存 与 召回率 的平衡, 1024 维 COSINE 取 24 召回 99%+)
_HNSW_M = 24
# HNSW 索引: 构建时候选队列长度
_HNSW_EF_CONSTRUCTION = 150
# HNSW 检索: 候选队列长度下限(ef 必须 >= limit, 取 max 保证召回)
_HNSW_EF_BASE = 64


def _to_milvus_expr(where: str) -> str:
    """SQL 风格谓词转 Milvus 表达式

    Milvus 布尔表达式的列表成员判断用方括号: `field in ['a','b']`,
    调用方(SQLModel/LanceDB 口径)书写的是 `field IN ('a','b')`, 此处统一转换;
    == 与比较运算符两者语法一致, 无需处理。
    """
    return _SQL_IN_RE.sub(lambda m: f"in [{m.group(1)}]", where)


def _hit_to_row(hit: Any, output_fields: list[str] | None) -> dict:
    """pymilvus 检索命中 → 行数据 dict(附 _distance)

    pymilvus search 返回的 hit 是 dict 子类 Hit({'id','distance','entity'}),
    内层 entity 才是行字段数据——直接 `dict(hit.entity)` 会把 Hit 自身的
    id/distance/entity 当成行字段(属性 .entity 返回 Hit 自身而非内层 dict)。
    兼容旧版 Hit 对象(属性访问)与无 entity 包装的返回结构。
    """
    if isinstance(hit, dict):
        entity = hit.get("entity")
        distance = hit.get("distance", 0.0)
    else:  # 旧版 Hit 对象: 属性访问
        entity = getattr(hit, "entity", hit)
        distance = getattr(hit, "distance", 0.0)
    if isinstance(entity, dict):
        row = dict(entity)
    elif entity is not None and hasattr(entity, "get"):
        # 旧版实体对象: 按请求字段逐个取
        row = {k: entity.get(k) for k in (output_fields or [])}
    else:  # 无 entity 包装: hit 自身即行数据
        row = dict(hit) if isinstance(hit, dict) else {}
    row["_distance"] = distance
    return row


def _build_py2sql_type_map() -> dict[str, DataType]:
    """构建 Python 类型名 -> Milvus DataType 映射(需先 import pymilvus)"""
    from pymilvus import DataType

    return {
        "bool": DataType.BOOL,
        "int": DataType.INT64,
        "float": DataType.DOUBLE,
        "str": DataType.VARCHAR,
        "datetime": DataType.TIMESTAMPTZ,  # Milvus 中用整数表示时间戳
        "list": DataType.ARRAY,  # 数组字段(元素类型在建表时进一步解析)
        "dict": DataType.JSON,  # 复杂类型用 JSON 表示
    }


class DBVectorMilvus(DBVectorInterface):
    """Milvus 向量数据库实现

    注: 单表必须有主键, str 字段必须通过 Field(json_schema_extra={"max_length": N})
    或 MaxLen 元数据声明长度(Milvus VARCHAR 必填 max_length)。
    """

    def __init__(self, milvus_config: MilvusConfig) -> None:
        """初始化(仅记录配置, 连接与 SDK 加载延迟到 connect/_ensure_client)"""
        self.milvus_config = milvus_config
        self.async_vector: AsyncMilvusClient | None = None
        # Python 类型名 -> DataType 映射(import pymilvus 后惰性构建缓存)
        self._py2sql_type: dict[str, DataType] | None = None
        # 集合存在性缓存(检索热路径免 describe/list 往返; None=未加载)
        self._known_collections: set[str] | None = None

    # ############################# 连接管理 #############################

    def _resolve_uri(self) -> str:
        """组装连接地址: 优先 uri, 否则 host:port"""
        cfg = self.milvus_config
        return cfg.uri or f"{cfg.host}:{cfg.port}"

    async def connect(self, log_bool: bool = False) -> None:
        """建立 Milvus 连接(首次调用时加载 pymilvus; 目标库不存在时自动创建)"""
        from pymilvus import AsyncMilvusClient

        try:
            cfg = self.milvus_config
            uri = self._resolve_uri()
            # 认证参数(探测连接与正式连接共用)
            auth_kwargs: dict[str, Any] = {}
            if cfg.token:
                auth_kwargs["token"] = cfg.token
            elif cfg.user and cfg.password:
                auth_kwargs.update({"user": cfg.user, "password": cfg.password})

            # 直连不存在的 db_name 会报错, 先以默认连接探测: 目标库缺失时自动创建
            bootstrap = AsyncMilvusClient(uri=uri, **auth_kwargs)
            try:
                try:
                    names = await bootstrap.list_databases()
                    # 兼容 list_databases 返回 str 或 DatabaseInfo 对象
                    db_names = [n if isinstance(n, str) else getattr(n, "db_name", str(n)) for n in names]
                    if cfg.database not in db_names:
                        await bootstrap.create_database(db_name=cfg.database)
                        logger.info(f"Milvus 数据库 {cfg.database} 不存在, 已自动创建")
                except Exception as probe_err:
                    # 老版本 milvus 不支持 database 管理或网络抖动: 仅告警, 继续按原配置直连
                    logger.warning(f"Milvus 数据库探测跳过(不影响连接): {probe_err}")
            finally:
                await bootstrap.close()

            # 正式连接目标库
            self.async_vector = AsyncMilvusClient(db_name=cfg.database, uri=uri, **auth_kwargs)

            if log_bool:
                logger.info(f"Milvus数据库连接成功: {uri}, db={cfg.database}")
        except Exception as e:
            raise Exception(f"Milvus数据库连接失败: {e}") from e

    async def _ensure_client(self) -> AsyncMilvusClient:
        """获取客户端(自愈式: 连接未建立时先建连接, web/worker/脚本直跑均安全)"""
        if self.async_vector is None:
            await self.connect()
        return self.async_vector

    async def is_connected(self) -> bool:
        """检查连接状态(能否执行一次服务端往返)"""
        if self.async_vector is None:
            return False
        try:
            await self.async_vector.list_collections()
            return True
        except Exception:
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self.async_vector is not None:
            await self.async_vector.close()
            self.async_vector = None

    async def reconnect(self) -> None:
        """重新连接"""
        await self.disconnect()
        await self.connect()

    # ############################# Schema 构建 #############################

    def _type_map(self) -> dict[str, DataType]:
        """获取类型映射(首次调用时构建并缓存)"""
        if self._py2sql_type is None:
            self._py2sql_type = _build_py2sql_type_map()
        return self._py2sql_type

    def _field_extra(self, field_info) -> dict:
        """安全读取 Field json_schema_extra(非 dict 时返回空)"""
        extra = getattr(field_info, "json_schema_extra", None)
        return extra if isinstance(extra, dict) else {}

    def _is_primary(self, field_info) -> bool:
        """判断字段是否主键(兼容 Pydantic V2: json_schema_extra 声明或 primary_key 元数据)

        注意: sqlmodel FieldInfo 的 primary_key 默认值是 PydanticUndefined,
        直接 getattr 会把未声明主键的字段误判为主键, 必须显式排除。
        """
        if self._field_extra(field_info).get("primary_key", False):
            return True
        pk_val = getattr(field_info, "primary_key", False)
        return bool(pk_val) and pk_val is not PydanticUndefined

    async def _build_schema(self, schema_cls: type[BaseModel], vector_dims: dict[str, int]) -> CollectionSchema:
        """把 Pydantic 模型转换为 Milvus CollectionSchema(纯稠密口径, 无 BM25 函数)"""
        from pymilvus import CollectionSchema, DataType, FieldSchema

        type_map = self._type_map()
        fields: list[FieldSchema] = []
        primary_count = 0

        for field_name, field_info in schema_cls.model_fields.items():
            extra = self._field_extra(field_info)
            is_primary = self._is_primary(field_info)
            if is_primary:
                primary_count += 1
                if primary_count > 1:
                    raise ValueError(f"模型 {schema_cls.__name__} 只允许一个主键")

            if field_name in vector_dims:
                # 向量字段: FLOAT_VECTOR(dim)
                fields.append(
                    FieldSchema(field_name, DataType.FLOAT_VECTOR, dim=vector_dims[field_name])
                )
                continue

            # 显式声明为 JSON 字段的复杂类型(BaseModel/dict 注解等)
            if extra.get("milvus_dtype") == "JSON":
                fields.append(FieldSchema(name=field_name, dtype=DataType.JSON, is_primary=is_primary))
                continue

            # 常规字段: 按 Python 类型名映射
            annotation = field_info.annotation
            # Optional 剥离: Union[X, None] -> X(如 str | None -> str, 否则无法识别)
            union_args = get_args(annotation)
            if union_args and type(None) in union_args:
                non_none = [a for a in union_args if a is not type(None)]
                if len(non_none) == 1:
                    annotation = non_none[0]
            # 枚举类型按字符串存储(model_dump 后为 str 值)
            if isinstance(annotation, type) and issubclass(annotation, Enum):
                annotation = str
            type_name = getattr(annotation, "__name__", str(annotation))
            sql_type = type_map.get(type_name)
            if sql_type is None:
                # 对齐源项目口径: 未知类型回退 VARCHAR(255) 而非 JSON, 保留可过滤性
                logger.warning(
                    f"未定义 Python 类型 {type_name!r} 的 Milvus 映射, 字段 {field_name} 回退为 VARCHAR(255) 存储"
                )
                sql_type = DataType.VARCHAR

            # ARRAY 字段需指定元素类型; 元素为复杂类型时回退 JSON 存储
            if sql_type == DataType.ARRAY:
                args = getattr(annotation, "__args__", ())
                elem_name = getattr(args[0], "__name__", str(args[0])) if args else None
                if elem_name and elem_name in type_map:
                    element_type = type_map[elem_name]
                else:
                    fields.append(FieldSchema(name=field_name, dtype=DataType.JSON, is_primary=is_primary))
                    continue
                # ARRAY<VARCHAR> 需指定元素 max_length, 并限制最大元素数
                field_kwargs: dict[str, Any] = {
                    "name": field_name,
                    "dtype": DataType.ARRAY,
                    "is_primary": is_primary,
                    "element_type": element_type,
                    "max_capacity": 64,
                }
                if element_type == DataType.VARCHAR:
                    field_kwargs["max_length"] = 255
                fields.append(FieldSchema(**field_kwargs))
                continue

            if sql_type == DataType.VARCHAR:
                # VARCHAR 必填 max_length: json_schema_extra.max_length / MaxLen 元数据 / 默认 255
                max_length = extra.get("max_length", 255)
                for meta in field_info.metadata:
                    if isinstance(meta, MaxLen):
                        max_length = meta.max_length
                        break
                fields.append(
                    FieldSchema(
                        name=field_name,
                        dtype=DataType.VARCHAR,
                        is_primary=is_primary,
                        max_length=max_length,
                    )
                )
                continue

            fields.append(FieldSchema(name=field_name, dtype=sql_type, is_primary=is_primary))

        return CollectionSchema(fields, description=f"Schema for {schema_cls.__name__.lower()}")

    async def _create_hnsw_index(self, collection_name: str, vector_dims: dict[str, int]) -> None:
        """为全部向量字段创建 HNSW COSINE 索引"""
        from pymilvus import AsyncMilvusClient

        index_params = AsyncMilvusClient.prepare_index_params()
        for field_name in vector_dims:
            index_params.add_index(
                field_name=field_name,
                index_type="HNSW",
                index_name=f"{collection_name}_{field_name}_index",
                metric_type="COSINE",
                params={"M": _HNSW_M, "efConstruction": _HNSW_EF_CONSTRUCTION},
            )
        await self.async_vector.create_index(collection_name, index_params)

    # ############################# 表生命周期 #############################

    async def create_table(
        self,
        schema_cls: type[BaseModel],
        vector_dims: dict[str, int] = {"vector": 1024},
    ) -> None:
        """创建 Milvus 集合(已存在时跳过), 并建 HNSW 索引后加载进内存"""
        try:
            client = await self._ensure_client()
            collection_name = schema_cls.__name__.lower()

            if await client.has_collection(collection_name):
                logger.warning(f"集合 {collection_name} 已存在")
                return

            schema = await self._build_schema(schema_cls, vector_dims)
            await client.create_collection(collection_name, schema=schema)
            await self._create_hnsw_index(collection_name, vector_dims)
            await client.load_collection(collection_name)
            # 同步集合缓存, 供 table_exists 免 RPC 命中
            if self._known_collections is not None:
                self._known_collections.add(collection_name)
            logger.info(f"Milvus 集合 {collection_name} 创建并加载成功")
        except Exception as e:
            raise Exception(f"Milvus创建集合失败: {e}") from e

    async def create_all(self) -> None:
        """自动发现未创建的向量表: 遍历注册表, 仅创建远端不存在的集合(幂等)"""
        client = await self._ensure_client()
        existing = set(await client.list_collections())
        for table_name, schema_cls in VectorModel.registry.items():
            if table_name in existing:
                logger.info(f"向量表 {table_name} 已存在, 跳过")
                continue
            # 从模型 json_schema_extra 自动提取向量维度(如 embedding=1024), 无需手动传参
            await self.create_table(schema_cls, schema_cls.vector_dims())
            logger.info(f"Milvus 向量表已创建: {table_name}")

    async def load_all(self) -> None:
        """加载全部集合进查询内存(Milvus 检索前必须 load)"""
        client = await self._ensure_client()
        for collection_name in await client.list_collections():
            await client.load_collection(collection_name)

    async def table_exists(self, table_name: str) -> bool:
        """判断向量表(集合)是否存在(带缓存: 首次加载列表后热路径零 RPC)"""
        client = await self._ensure_client()
        if self._known_collections is None:
            self._known_collections = set(await client.list_collections())
        if table_name in self._known_collections:
            return True
        # 缓存未命中: 实际查一次(覆盖他处新建的场景)并回填缓存
        if await client.has_collection(table_name):
            self._known_collections.add(table_name)
            return True
        return False

    async def drop_table(self, table_name: str) -> None:
        """删除向量表(不存在时静默跳过)"""
        if await self.table_exists(table_name):
            await (await self._ensure_client()).drop_collection(table_name)
            if self._known_collections is not None:
                self._known_collections.discard(table_name)

    async def get_vector_dim(self, table_name: str, field: str = "embedding") -> int | None:
        """读取集合中向量字段的维度(表或字段不存在返回 None)

        用于全库重向量化时对比新旧模型维度。
        """
        from pymilvus import DataType

        if not await self.table_exists(table_name):
            return None
        desc = await (await self._ensure_client()).describe_collection(table_name)
        for fs in desc.fields:
            if fs.name == field and fs.dtype == DataType.FLOAT_VECTOR:
                return fs.params.get("dim")
        return None

    # ############################# 数据操作 #############################

    async def add(self, data_list_class: list[BaseModel]) -> None:
        """向集合批量插入数据(模型实例列表)

        None 值兜底: pymilvus 对非 nullable 字段传 nil 直接报错
        (varchar 字段报 "array type mismatch ... got nil", 措辞误导),
        JSON 字段 None 补空 dict, VARCHAR 字段 None 补空串。
        """
        if not data_list_class:
            return

        client = await self._ensure_client()
        model_cls = data_list_class[0].__class__
        collection_name = model_cls.__name__.lower()

        # 预扫描 JSON 与 VARCHAR(str) 类型字段
        json_fields: set[str] = set()
        varchar_fields: set[str] = set()
        for fname, finfo in model_cls.model_fields.items():
            if self._field_extra(finfo).get("milvus_dtype") == "JSON":
                json_fields.add(fname)
                continue
            # Optional[str] 剥离 None 位得 str
            args = [a for a in get_args(finfo.annotation) if a is not type(None)]
            base = args[0] if args else finfo.annotation
            if base is str:
                varchar_fields.add(fname)

        data_list_dict = []
        for item in data_list_class:
            item_dict = item.model_dump()
            for fname in json_fields:
                if item_dict.get(fname) is None:
                    item_dict[fname] = {}
            for fname in varchar_fields:
                if item_dict.get(fname) is None:
                    item_dict[fname] = ""
            data_list_dict.append(item_dict)

        # 分批并发插入: 单 RPC 过大拖慢网络传输, 批间并发重叠往返
        if len(data_list_dict) <= _INSERT_BATCH:
            await client.insert(collection_name, data_list_dict)
            return
        batches = [data_list_dict[i : i + _INSERT_BATCH] for i in range(0, len(data_list_dict), _INSERT_BATCH)]
        semaphore = asyncio.Semaphore(_INSERT_CONCURRENCY)

        async def _insert(batch: list[dict]) -> None:
            async with semaphore:
                await client.insert(collection_name, batch)

        await asyncio.gather(*(_insert(batch) for batch in batches))

    async def delete_by_filter(self, table_name: str, where: str) -> None:
        """按谓词删除数据(如 'document_id == "xxx"')

        不主动 flush: 删除在已 load 内存中立即可见, 持久化由 Milvus 自动落盘;
        同步 flush 每次数秒, 高频入库(删旧插新)场景是主要拖累。
        """
        client = await self._ensure_client()
        await client.delete(table_name, filter=_to_milvus_expr(where))

    async def query_by_filter(
        self,
        table_name: str,
        where: str,
        output_fields: list[str],
        limit: int | None = None,
    ) -> list[dict]:
        """按谓词读取行(标量过滤查询, 不涉及向量)"""
        client = await self._ensure_client()
        kwargs: dict[str, Any] = {"filter": _to_milvus_expr(where), "output_fields": output_fields}
        if limit is not None:
            kwargs["limit"] = limit
        return await client.query(table_name, **kwargs)

    async def search(
        self,
        schema_cls: type[BaseModel],
        query_vector: list[float],
        vector_dims_key: str = "embedding",
        limit: int = 5,
    ) -> list[BaseModel]:
        """向量相似检索, 返回模型实例列表"""
        client = await self._ensure_client()
        collection_name = schema_cls.__name__.lower()
        results = await client.search(
            collection_name,
            [query_vector],  # Milvus 期望批次格式
            anns_field=vector_dims_key,
            limit=limit,
            output_fields=list(schema_cls.model_fields.keys()),
            # HNSW 索引检索参数为 ef(nprobe 仅对 IVF 系列生效), ef>=limit 保证召回
            search_params={"metric_type": "COSINE", "params": {"ef": max(_HNSW_EF_BASE, limit)}},
        )
        items: list[BaseModel] = []
        for hits in results:
            for hit in hits:
                data = _hit_to_row(hit, list(schema_cls.model_fields.keys()))
                items.append(schema_cls.model_validate(data))
        return items

    async def search_filtered(
        self,
        table_name: str,
        query_vector: list[float],
        where: str | None = None,
        output_fields: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """向量相似检索(可选谓词预过滤), 返回含 _distance 的原始行

        与 LanceDB 实现的返回约定对齐: 每行为字段 dict + `_distance`
        (此处为 COSINE 距离 = 1 - cos_sim, 越小越相关),
        上层 score=1/(1+_distance) 的单调映射口径不变。
        """
        client = await self._ensure_client()
        if not await self.table_exists(table_name):
            logger.warning(f"Milvus 集合 {table_name} 不存在, 返回空结果")
            return []

        kwargs: dict[str, Any] = {
            "anns_field": "embedding",
            "limit": limit,
            "output_fields": output_fields or ["*"],
            # HNSW 索引检索参数为 ef(nprobe 仅对 IVF 系列生效), ef>=limit 保证召回
            "search_params": {"metric_type": "COSINE", "params": {"ef": max(_HNSW_EF_BASE, limit)}},
        }
        if where:
            kwargs["filter"] = _to_milvus_expr(where)
        results = await client.search(table_name, [query_vector], **kwargs)

        rows: list[dict] = []
        for hits in results:
            for hit in hits:
                rows.append(_hit_to_row(hit, output_fields))
        return rows
