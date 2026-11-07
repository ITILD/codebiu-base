"""数据库工厂: 按配置装配关系/缓存/向量库实现(生产栈: postgres/redis/milvus)"""

from common.utils.db.do.db_config import DBConfig
from common.utils.db.session.interface.db_relational_interface import (
    DBRelationInterface,
)
from common.utils.db.session.interface.db_cache_interface import DBCacheInterface
from common.utils.db.session.interface.db_vector_interface import DBVectorInterface


class DBFactory:
    """根据配置创建数据库连接(各实现类延迟导入, 未启用的后端不在启动时加载 SDK)"""

    @classmethod
    def create_rel(cls, db_config: DBConfig) -> DBRelationInterface:
        from common.utils.db.session.impl.db_postgre import DBPostgre

        return DBPostgre(db_config)

    @classmethod
    def create_cache(cls, db_config: DBConfig) -> DBCacheInterface:
        from common.utils.db.session.impl.db_cache_redis import DBCacheRedis

        return DBCacheRedis(db_config)

    @classmethod
    def create_vector(cls, db_config: DBConfig) -> DBVectorInterface:
        from common.utils.db.session.impl.db_vector_milvus import DBVectorMilvus

        return DBVectorMilvus(db_config)
