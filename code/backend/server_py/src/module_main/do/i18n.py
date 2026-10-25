"""系统主模块 多语言词条覆盖表模型与请求/响应体定义

按 key 维度覆盖前端默认词条: 任一语言列为 NULL/空串表示"不覆盖该语言",
由前端回退到内置默认文案(应用启动时全量拉取做热更新)。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel

# 支持覆盖的语言列(与前端 locale 文件名一致)
I18N_LANGUAGES: tuple[str, ...] = ("zh", "ja", "en")


def _utcnow() -> datetime:
    """UTC 当前时间(全部时间戳统一 UTC 存储)"""
    return datetime.now(timezone.utc)


class I18nOverride(SQLModel, table=True):
    """词条覆盖表(key 主键; 一语言一列, 空值即不覆盖)"""

    __tablename__ = "i18n_override"

    key: str = Field(
        primary_key=True,
        max_length=500,
        description="词条唯一键(前后端约定的 i18n key, 如 common.save)",
    )
    zh: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="中文覆盖文案(NULL/空串=不覆盖)",
    )
    ja: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="日文覆盖文案(NULL/空串=不覆盖)",
    )
    en: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="英文覆盖文案(NULL/空串=不覆盖)",
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=_utcnow,
            nullable=False,
        ),
        description="最后更新时间(UTC)",
    )


# ################ 请求/响应体 ################


class I18nOverrideItem(SQLModel):
    """单条词条覆盖(导入/批量写入共用)

    未传入的语言字段视为"不修改"; 显式传入空串视为"不覆盖该语言"(存 NULL)。
    """

    key: str = Field(description="词条唯一键")
    zh: str | None = Field(default=None, description="中文覆盖文案")
    ja: str | None = Field(default=None, description="日文覆盖文案")
    en: str | None = Field(default=None, description="英文覆盖文案")


class I18nOverrideBulkPut(SQLModel):
    """批量 upsert 请求体"""

    items: list[I18nOverrideItem] = Field(default_factory=list, description="待写入词条列表")


class I18nOverrideResponse(SQLModel):
    """词条覆盖响应(管理端列表)"""

    key: str
    zh: str | None = None
    ja: str | None = None
    en: str | None = None
    updated_at: datetime


class I18nExportItem(SQLModel):
    """导出的单条词条(不含时间戳)"""

    key: str
    zh: str | None = None
    ja: str | None = None
    en: str | None = None


class I18nExportResponse(SQLModel):
    """导出响应"""

    items: list[I18nExportItem]


class I18nImportRequest(SQLModel):
    """导入请求体"""

    items: list[I18nOverrideItem] = Field(default_factory=list, description="待导入词条列表")
    overwrite: bool = Field(default=False, description="True=覆盖已存在词条, False=跳过")


class I18nCountResponse(SQLModel):
    """写入条数响应"""

    count: int


class I18nImportResponse(SQLModel):
    """导入结果(写入条数 + 被跳过的 key 列表)"""

    count: int
    skipped: list[str]
