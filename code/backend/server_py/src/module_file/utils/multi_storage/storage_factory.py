"""存储工厂: 按配置装配 S3 实现"""

from module_file.utils.multi_storage.do.storage_config import StorageConfig
from module_file.utils.multi_storage.session.interface.storage_interface import StorageInterface


class StorageFactory:
    @staticmethod
    def create(storage_config: StorageConfig) -> StorageInterface:
        """
        根据配置创建 S3 兼容存储对象(rustfs/MinIO 等)

        aioboto3 重量级 SDK 延迟导入: 仅在创建存储时加载
        """
        from module_file.utils.multi_storage.session.impl.storage_s3 import (
            S3StorageInterface,
        )

        return S3StorageInterface(storage_config)
