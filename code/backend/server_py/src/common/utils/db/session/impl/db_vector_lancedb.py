"""LanceDB 向量库实现(可选向量后端: 依赖不随基线打包, 使用时按需安装)

基线不再把 lancedb/pyarrow 打进默认依赖, 原因:
- 包体积大(lancedb+pyarrow 约 220MB), 仅向量场景需要
- 部署侧可切换其他向量后端(如 milvus), 未启用时不应背负 SDK

按需安装: uv pip install "lancedb==0.30.0" "pyarrow>=22.0.0"
未安装时: 启动不受影响(connect 失败仅告警跳过), 调用向量接口时给出安装提示。
"""

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from lancedb import connect_async, AsyncConnection, AsyncTable
    from lancedb.pydantic import LanceModel, Vector
from pydantic import BaseModel
from common.utils.db.do.db_config import LancedbConfig
from common.utils.db.session.interface.db_vector_interface import DBVectorInterface
from common.utils.db.orm.vector_model import VectorModel
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DBVectorLancedb(DBVectorInterface):
    """
    LanceDB向量数据库实现
    封装向量数据库操作
    """

    database: str = None
    async_vector: AsyncConnection = None

    def __init__(self, lancedb_config: LancedbConfig):
        """
        初始化LanceDB向量数据库连接

        Args:
            lancedb_config: LanceDB数据库配置对象
        """
        self.database = Path(lancedb_config.database).resolve().as_posix()

    async def connect(self, log_bool=False):
        """
        建立数据库连接

        Args:
            log_bool: 是否启用日志
        """
        try:
            from lancedb import connect_async

            # 创建LanceDB客户端实例
            self.async_vector = await connect_async(self.database)

            if log_bool:
                logger.info(f"LanceDB数据库连接成功: {self.database}")
        except ImportError as e:
            # 依赖未随基线打包: 明确提示安装方式, 而非笼统的"连接失败"
            raise Exception(
                "lancedb 未安装(基线默认不打包该依赖): 请执行 uv pip install 'lancedb==0.30.0' pyarrow"
            ) from e
        except Exception as e:
            raise Exception(f"LanceDB数据库连接失败: {e}")

    async def _table(self, table_name: str) -> AsyncTable:
        """打开表(自愈式: 连接未建立时先建连接, web/worker/脚本直跑均安全)"""
        if self.async_vector is None:
            await self.connect()
        return await self.async_vector.open_table(table_name)

    async def create_table(
        self,
        schema_cls: type[BaseModel],
        vector_dims: dict[str, int] = {"vector": 1024},
    ) -> AsyncTable:
        """
        创建 LanceDB 表结构（空表）

        Args:
            schema_cls: 原始 Pydantic 模型类（BaseModel 子类）
            vector_dims: 向量字段名 -> 维度 的映射
        """
        try:
            if self.async_vector is None:
                await self.connect()
            table_name = schema_cls.__name__.lower()
            lance_model_cls = self._convert_to_lance_model(schema_cls, vector_dims)
            # 通过 schema= 传入模型类，data=None 表示空表
            async_table = await self.async_vector.create_table(
                table_name,
                data=None,  # 明确无初始数据
                schema=lance_model_cls,
                mode="overwrite",  # 覆盖,避免表已存在报错
            )
            return async_table

        except Exception as e:
            raise Exception(f"LanceDB创建表失败: {e}") from e

    def _convert_to_lance_model(
        self,
        schema_cls: type[BaseModel],
        vector_dims: dict[str, int] = {"vector": 1024},
    ) -> type[LanceModel]:
        """
        将 Pydantic BaseModel 类转换为 LanceModel 子类。
        向量字段使用 Vector(dim)，其他字段保留原注解。
        """
        from lancedb.pydantic import LanceModel,Vector
        annotations = {}
        for name, field in schema_cls.model_fields.items():
            if name in vector_dims:
                # 使用 Vector(dim) 表示向量字段
                annotations[name] = Vector(vector_dims[name])
            else:
                # 保留原始类型注解
                annotations[name] = field.annotation

        # 动态创建 LanceModel 子类
        return type(
            schema_cls.__name__,
            (LanceModel,),
            {
                "__annotations__": annotations,
                "__doc__": f"Lance model for {schema_cls.__name__}",
            },
        )

    async def add(
        self,
        data_list_class: list[BaseModel],
    ) -> None:
        """
        向 LanceDB 表中添加数据。

        Args:
            data_list_class: 要添加的数据列表
        """
        table_name = data_list_class[0].__class__.__name__.lower()
        async_table = await self._table(table_name)
        data_list_dict = [item.model_dump() for item in data_list_class]
        await async_table.add(data_list_dict)

    async def search(
        self,
        schema_cls: type[BaseModel],
        query_vector: list[float],
        vector_dims_key: str = "vector",
    ) -> list[type[BaseModel]]:
        """
        查询 LanceDB 表中与查询向量最相似的记录。

        Args:
            schema_cls: 原始 Pydantic 模型类（BaseModel 子类）
            query_vector: 查询向量
        """
        table_name = schema_cls.__name__.lower()
        async_table = await self._table(table_name)
        async_results = await async_table.search(query_vector)
        # 排除向量字段，只返回其他字段
        query_fields = [
            field
            for field in schema_cls.model_fields.keys()
            if field != vector_dims_key
        ]
        # query_fields.append('_distance')
        result_temp = await async_results.select(query_fields).to_list()

        result: list[type[BaseModel]] = [
            schema_cls.model_validate(item) for item in result_temp
        ]
        return result

    # ############################# 注册表批量操作 #############################

    async def create_all(self) -> None:
        """创建所有已注册向量表(VectorModel.registry; 幂等: 已存在的表跳过, 不覆盖数据)"""
        existing = set(await self.async_vector.table_names())
        for name, cls in VectorModel.registry.items():
            if name in existing:
                continue
            await self.create_table(cls, cls.vector_dims())
            logger.info(f"LanceDB 向量表已创建: {name}")

    async def load_all(self) -> None:
        """LanceDB 无需预加载(无 Milvus load collection 语义), 保留接口与 connect_all 流程兼容"""
        return None

    # ############################# 表级通用操作 #############################

    async def table_exists(self, table_name: str) -> bool:
        """判断向量表是否存在"""
        if self.async_vector is None:
            await self.connect()
        return table_name in await self.async_vector.table_names()

    async def drop_table(self, table_name: str) -> None:
        """删除向量表(不存在时静默跳过)"""
        if await self.table_exists(table_name):
            await self.async_vector.drop_table(table_name)

    async def delete_by_filter(self, table_name: str, where: str) -> None:
        """按 SQL 谓词删除行(表不存在时告警跳过)

        Args:
            table_name: 表名
            where: SQL 谓词, 如 'document_id == "xxx"'
        """
        if not await self.table_exists(table_name):
            logger.warning(f"LanceDB 表 {table_name} 不存在, 跳过删除")
            return
        table = await self.async_vector.open_table(table_name)
        await table.delete(where)

    async def query_by_filter(
        self,
        table_name: str,
        where: str,
        output_fields: list[str],
        limit: int | None = None,
    ) -> list[dict]:
        """按谓词读取行(标量过滤查询, 不涉及向量)

        Args:
            table_name: 表名
            where: SQL 谓词
            output_fields: 返回字段列表
            limit: 最大行数(None 不限)
        """
        if not await self.table_exists(table_name):
            return []
        table = await self.async_vector.open_table(table_name)
        query = table.query().where(where).select(output_fields)
        if limit is not None:
            query = query.limit(limit)
        return await query.to_list()

    async def search_filtered(
        self,
        table_name: str,
        query_vector: list[float],
        where: str | None = None,
        output_fields: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """向量相似检索(可选谓词预过滤), 返回含 _distance 的原始行

        Args:
            table_name: 表名
            query_vector: 查询向量
            where: SQL 谓词预过滤(None 不过滤)
            output_fields: 返回字段列表(None 返回全部字段)
            limit: 返回条数
        """
        if not await self.table_exists(table_name):
            logger.warning(f"LanceDB 表 {table_name} 不存在, 返回空结果")
            return []
        table = await self.async_vector.open_table(table_name)
        query = table.search(query_vector)
        if where:
            query = query.where(where, prefilter=True)
        if output_fields:
            query = query.select(output_fields)
        return await query.limit(limit).to_list()

    async def get_vector_dim(
        self, table_name: str, field: str = "embedding"
    ) -> int | None:
        """从 Arrow schema 解析向量字段维度(表或字段不存在返回 None)

        用于全库重向量化时对比新旧模型维度。
        """
        if not await self.table_exists(table_name):
            return None
        table = await self.async_vector.open_table(table_name)
        schema = await table.schema()
        for item in schema:
            if item.name == field:
                return getattr(item.type, "list_size", None)
        return None
