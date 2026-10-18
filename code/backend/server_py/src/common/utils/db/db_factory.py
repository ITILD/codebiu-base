"""数据库工厂: 按配置装配关系/缓存/向量库实现"""

from common.utils.db.do.db_config import (
    DBConfig,
    PostgresConfig,
    RedisConfig,
)
from common.utils.db.session.interface.db_relational_interface import (
    DBRelationInterface,
)
from common.utils.db.session.interface.db_cache_interface import DBCacheInterface
from common.utils.db.session.interface.db_vector_interface import DBVectorInterface


class DBFactory:
    """根据参数创建多种数据库连接

    各实现类延迟导入: 未启用的后端不会在启动时加载其 SDK
    """

    @classmethod
    def create_rel(cls, db_config: DBConfig) -> DBRelationInterface:
        if isinstance(db_config, PostgresConfig):
            from common.utils.db.session.impl.db_postgre import DBPostgre

            db_rel = DBPostgre(db_config)
        else:
            from common.utils.db.session.impl.db_sqlite import DBSqlite

            db_rel = DBSqlite(db_config)
        return db_rel

    # 缓存数据库连接
    @classmethod
    def create_cache(cls, db_config: DBConfig) -> DBCacheInterface:
        if isinstance(db_config, RedisConfig):
            from common.utils.db.session.impl.db_cache_redis import DBCacheRedis

            db_cache = DBCacheRedis(db_config)
        else:
            from common.utils.db.session.impl.db_cache_fakeredis import DBCacheFakeredis

            db_cache = DBCacheFakeredis(db_config)
        return db_cache

    # 向量数据库连接(按配置路由: milvus 远程实现 / lancedb 本地实现, SDK 均延迟导入)
    @classmethod
    def create_vector(cls, db_config: DBConfig) -> DBVectorInterface:
        from common.utils.db.do.db_config import MilvusConfig

        if isinstance(db_config, MilvusConfig):
            from common.utils.db.session.impl.db_vector_milvus import DBVectorMilvus

            return DBVectorMilvus(db_config)

        from common.utils.db.session.impl.db_vector_lancedb import DBVectorLancedb

        return DBVectorLancedb(db_config)
