"""系统主模块 多语言词条覆盖数据访问层"""

from datetime import datetime, timezone

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from common.config.db import DaoRel
from module_main.do.i18n import I18N_LANGUAGES, I18nOverride, I18nOverrideItem


class I18nDao:
    @DaoRel
    async def list_all(self, session: AsyncSession | None = None) -> list[I18nOverride]:
        """查询全部词条覆盖(按 key 升序)"""
        statement = select(I18nOverride).order_by(I18nOverride.key.asc())
        return list((await session.exec(statement)).all())

    @DaoRel
    async def bulk_upsert(
        self, items: list[I18nOverrideItem], session: AsyncSession | None = None
    ) -> int:
        """批量 upsert(单事务, 全成功或全回滚) :return: 写入条数"""
        for item in items:
            await self._apply(item, session)  # type: ignore[arg-type]
        return len(items)

    @DaoRel
    async def import_items(
        self,
        items: list[I18nOverrideItem],
        overwrite: bool = False,
        session: AsyncSession | None = None,
    ) -> tuple[int, list[str]]:
        """
        导入词条(单事务)
        :param items: 待导入词条
        :param overwrite: 已存在词条是否覆盖(False 时跳过并记入 skipped)
        :return: (写入条数, 跳过的 key 列表)
        """
        count = 0
        skipped: list[str] = []
        for item in items:
            existing = await session.get(I18nOverride, item.key)  # type: ignore[arg-type]
            if existing is not None and not overwrite:
                skipped.append(item.key)
                continue
            await self._apply(item, session)  # type: ignore[arg-type]
            count += 1
        return count, skipped

    @DaoRel
    async def delete(self, key: str, session: AsyncSession | None = None) -> None:
        """按 key 删除词条覆盖(不存在时静默, 幂等)"""
        statement = delete(I18nOverride).where(I18nOverride.key == key)
        await session.exec(statement)
        await session.flush()

    async def _apply(self, item: I18nOverrideItem, session: AsyncSession) -> None:
        """写入单条词条(存在则更新显式传入的语言列, 否则新建)"""
        row = await session.get(I18nOverride, item.key)
        if row is None:
            row = I18nOverride(key=item.key)
            session.add(row)
        for lang in I18N_LANGUAGES:
            # 未显式传入的语言保持原值; 显式传入(含空串归一化后的 NULL)才写入
            if lang in item.model_fields_set:
                setattr(row, lang, getattr(item, lang))
        row.updated_at = datetime.now(timezone.utc)  # 显式刷新 UTC 时间
        await session.flush()
