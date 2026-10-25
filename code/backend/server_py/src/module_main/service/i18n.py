"""系统主模块 多语言词条覆盖业务逻辑层

约定:
    - key 写入前统一去首尾空白, 空 key 直接拒绝(400)
    - 语言值为空白字符串时归一化为 None(即"不覆盖该语言")
    - 批量写入/导入各自在 DAO 内单事务完成
"""

from common.utils.fastapi_ex.exceptions import BusinessError
from module_main.dao.i18n import I18nDao
from module_main.do.i18n import (
    I18N_LANGUAGES,
    I18nCountResponse,
    I18nExportItem,
    I18nExportResponse,
    I18nImportRequest,
    I18nImportResponse,
    I18nOverrideBulkPut,
    I18nOverrideItem,
    I18nOverrideResponse,
)


class I18nService:
    """多语言词条覆盖服务"""

    def __init__(self, dao: I18nDao):
        """依赖注入构造器: 初始化词条数据访问对象"""
        self.dao = dao

    @staticmethod
    def _normalize(item: I18nOverrideItem) -> I18nOverrideItem:
        """规范化单条词条: key 去空白(空则 400), 语言值去空白且空串转 None

        仅保留请求中显式传入的语言字段(未传入=不修改)。
        """
        key = item.key.strip()
        if not key:
            raise BusinessError("词条 key 不能为空")
        payload: dict[str, str | None] = {"key": key}
        for lang in I18N_LANGUAGES:
            if lang not in item.model_fields_set:
                continue
            value = getattr(item, lang)
            text = value.strip() if isinstance(value, str) else None
            payload[lang] = text or None
        return I18nOverrideItem.model_validate(payload)

    async def list_all(self) -> list[I18nOverrideResponse]:
        """全量查询词条覆盖(按 key 升序)"""
        rows = await self.dao.list_all()
        return [
            I18nOverrideResponse(
                key=row.key,
                zh=row.zh,
                ja=row.ja,
                en=row.en,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def bulk_put(self, data: I18nOverrideBulkPut) -> I18nCountResponse:
        """批量 upsert 词条覆盖"""
        items = [self._normalize(item) for item in data.items]
        if not items:
            return I18nCountResponse(count=0)
        return I18nCountResponse(count=await self.dao.bulk_upsert(items))

    async def delete(self, key: str) -> None:
        """删除单条词条覆盖(key 去空白; 不存在也返回成功, 幂等)"""
        normalized = key.strip()
        if not normalized:
            raise BusinessError("词条 key 不能为空")
        await self.dao.delete(normalized)

    async def export(self) -> I18nExportResponse:
        """导出全部词条覆盖(不含时间戳)"""
        rows = await self.dao.list_all()
        return I18nExportResponse(
            items=[
                I18nExportItem(key=row.key, zh=row.zh, ja=row.ja, en=row.en)
                for row in rows
            ]
        )

    async def import_items(self, data: I18nImportRequest) -> I18nImportResponse:
        """导入词条覆盖(overwrite=False 时已存在词条跳过并返回 skipped)"""
        items = [self._normalize(item) for item in data.items]
        if not items:
            return I18nImportResponse(count=0, skipped=[])
        count, skipped = await self.dao.import_items(items, overwrite=data.overwrite)
        return I18nImportResponse(count=count, skipped=skipped)
