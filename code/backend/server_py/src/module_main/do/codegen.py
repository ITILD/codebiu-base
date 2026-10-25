"""系统主模块 代码生成器请求/响应体定义

代码生成器只读取 ``SQLModel.metadata`` 的表元数据(不查库), 依据表结构生成
后端七层与前端模块脚手架。本文件仅放数据对象, 不含任何业务逻辑。
"""

from pydantic import BaseModel, Field, field_validator

# ############################### 表元数据 ###############################
class TableBrief(BaseModel):
    """表清单项(名称/注释/字段数)"""

    name: str = Field(..., description="表名")
    comment: str | None = Field(None, description="表注释")
    column_count: int = Field(..., description="字段数量")


class TableListResponse(BaseModel):
    """表清单响应"""

    items: list[TableBrief] = Field(default_factory=list, description="数据表列表")


class ColumnMeta(BaseModel):
    """表字段元数据(来自 SQLModel.metadata, 只读)"""

    name: str = Field(..., description="字段名")
    type: str = Field(..., description="归一化后的 Python 类型(str/int/float/bool/datetime/date/time/json/bytes)")
    sql_type: str = Field(..., description="数据库字段类型(如 VARCHAR(50))")
    nullable: bool = Field(..., description="是否允许为空")
    primary_key: bool = Field(..., description="是否主键")
    default: str | None = Field(None, description="字段默认值(可调用默认值不展开)")
    comment: str | None = Field(None, description="字段注释")
    max_length: int | None = Field(None, description="字符串最大长度")


class TableDetail(BaseModel):
    """表详情(含全部字段元数据)"""

    name: str = Field(..., description="表名")
    comment: str | None = Field(None, description="表注释")
    columns: list[ColumnMeta] = Field(default_factory=list, description="字段列表")


# ############################### 字段建议 ###############################
class ColumnSuggestion(BaseModel):
    """字段配置建议(启发式或 AI 推断结果)"""

    name: str = Field(..., description="字段名")
    label: str = Field(..., description="展示标签")
    control: str = Field("input", description="控件类型: input/textarea/number/switch/select/date/datetime")
    required: bool = Field(False, description="是否必填")
    searchable: bool = Field(False, description="是否作为查询条件")
    listable: bool = Field(True, description="是否在列表展示")
    editable: bool = Field(True, description="是否可编辑")
    dict_type: str | None = Field(None, description="关联字典类型编码")
    description: str = Field("", description="字段说明")
    width: int = Field(160, description="列表列宽(px)")

    @field_validator("label", "description", mode="before")
    @classmethod
    def _none_to_blank(cls, value):
        """前端表单可能提交 null: 归一为空串, 避免 422"""
        return "" if value is None else value

    @field_validator("control", mode="before")
    @classmethod
    def _none_to_input(cls, value):
        """控件类型缺省为文本框"""
        return value or "input"

    @field_validator("width", mode="before")
    @classmethod
    def _none_to_default_width(cls, value):
        """列宽缺省 160"""
        return 160 if value in (None, "") else value


class SuggestRequest(BaseModel):
    """字段建议请求"""

    table_name: str = Field(..., description="目标表名")
    use_ai: bool = Field(False, description="是否启用 AI 辅助(失败自动回退启发式规则)")
    module_name: str | None = Field(None, description="模块名(缺省由表名推导)")
    class_name: str | None = Field(None, description="类名(缺省由表名推导)")


class SuggestResponse(BaseModel):
    """字段建议响应"""

    module_name: str = Field(..., description="最终模块名(snake_case)")
    class_name: str = Field(..., description="最终类名(PascalCase)")
    page_title: str = Field(..., description="页面标题(默认取表注释)")
    columns: list[ColumnSuggestion] = Field(default_factory=list, description="字段配置建议")
    warnings: list[str] = Field(default_factory=list, description="命名推导/AI 回退等提示")
    ai_used: bool = Field(False, description="是否成功应用 AI 建议")


# ############################### 预览/生成 ###############################
class PreviewRequest(BaseModel):
    """代码预览请求"""

    table_name: str = Field(..., description="目标表名")
    module_name: str = Field(..., description="模块名(snake_case)")
    class_name: str = Field(..., description="类名(PascalCase)")
    page_title: str = Field("", description="页面标题(空则取表注释/类名)")
    columns: list[ColumnSuggestion] = Field(default_factory=list, description="字段配置")
    include_backend: bool = Field(True, description="是否生成后端七层")
    include_frontend: bool = Field(True, description="是否生成前端模块")

    @field_validator("page_title", mode="before")
    @classmethod
    def _none_to_blank(cls, value):
        """页面标题允许前端传 null(未填), 归一为空串后由服务端回退到表注释/类名"""
        return "" if value is None else value


class GeneratedFile(BaseModel):
    """单个生成文件"""

    path: str = Field(..., description="仓库根相对路径")
    language: str = Field(..., description="语言: python/typescript/vue")
    content: str = Field(..., description="文件内容")
    exists: bool = Field(False, description="目标文件是否已存在")


class PreviewResponse(BaseModel):
    """代码预览响应"""

    files: list[GeneratedFile] = Field(default_factory=list, description="生成文件列表")
    warnings: list[str] = Field(default_factory=list, description="注册/权限等提示")


class GenerateRequest(PreviewRequest):
    """代码生成请求(在预览参数上增加覆盖开关)"""

    overwrite: bool = Field(False, description="是否覆盖已存在文件")


class GenerateResponse(BaseModel):
    """代码生成响应"""

    written: list[str] = Field(default_factory=list, description="已写入文件(仓库根相对路径)")
    skipped: list[str] = Field(default_factory=list, description="已存在而跳过的文件")
    warnings: list[str] = Field(default_factory=list, description="注册/权限等提示")
