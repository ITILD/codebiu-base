"""系统主模块 代码生成器业务逻辑层

能力:
    - list_tables / get_table: 读取 SQLModel 注册表的表元数据(不查库)
    - suggest: 启发式推断字段控件/查询/列宽, 可选 AI 辅助(失败自动回退)
    - preview: 渲染后端七层 + 前端模块代码(不落盘)
    - generate: 按白名单根目录安全写盘(拒绝目录穿越, 默认不覆盖)

生成器不修改 app.py / 权限声明文件, 仅通过 warnings 提示人工补齐。
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from module_main.dao.codegen import CodegenDao
from module_main.do.codegen import (
    ColumnMeta,
    ColumnSuggestion,
    GenerateRequest,
    GenerateResponse,
    GeneratedFile,
    PreviewRequest,
    PreviewResponse,
    SuggestRequest,
    SuggestResponse,
    TableDetail,
    TableListResponse,
)
from module_main.utils.codegen.naming import (
    derive_names,
    pluralize,
    py_literal,
    python_annotation,
    sanitize_pascal,
    sanitize_snake,
    ts_type,
)
from module_main.utils.codegen.renderer import render

logger = logging.getLogger(__name__)

# AI 辅助超时(秒), 超时直接回退启发式规则
_AI_TIMEOUT = 30

# 允许的控件类型
_CONTROL_VALUES = frozenset(
    {"input", "textarea", "number", "switch", "select", "date", "datetime"}
)

# 审计字段(不作为业务可编辑字段)
_AUDIT_COLUMNS = ("created_at", "updated_at")

# 后端七层目录(生成新模块时按层补齐 __init__.py)
_LAYER_DIRS = frozenset({"do", "dao", "service", "controller", "dependencies"})

# 写盘白名单根目录(均以 __file__ 推导, 不依赖启动工作目录)
_SERVER_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _SERVER_ROOT / "src"
_REPO_ROOT = _SERVER_ROOT.parents[2]
_FRONTEND_SRC_ROOT = _REPO_ROOT / "code" / "frontend" / "vue3" / "src"

# AI 提示词: 只返回 JSON, 便于稳定解析
_AI_SYSTEM_PROMPT = """你是资深 Python FastAPI + Vue3 工程师, 负责为代码生成器补齐字段配置。
只输出一个 JSON 对象, 不要 markdown 代码块, 不要任何解释文字。
JSON 结构:
{
  "module_name": "snake_case 模块名",
  "class_name": "PascalCase 类名",
  "page_title": "中文页面标题",
  "columns": [
    {
      "name": "字段名",
      "label": "中文标签",
      "control": "input|textarea|number|switch|select|date|datetime",
      "searchable": true,
      "listable": true,
      "editable": true,
      "width": 160,
      "dict_type": "字典类型编码或 null"
    }
  ]
}
要求:
- 只能使用输入中存在的字段名;
- 主键与 created_at/updated_at 不可编辑(editable=false);
- 状态/类型类字段优先 select 或 switch, 日期字段用 date/datetime, 长文本用 textarea;
- width 取 90~260 之间整数。"""


@dataclass(slots=True)
class _Output:
    """待生成文件(绝对路径 + 语言 + 内容)"""

    path: Path
    language: str
    content: str


class CodegenService:
    """代码生成器服务"""

    def __init__(self, dao: CodegenDao | None = None):
        """依赖注入构造器: 初始化数据访问对象"""
        self.dao = dao or CodegenDao()

    # ############################### 表元数据 ###############################
    def list_tables(self, keyword: str | None = None) -> TableListResponse:
        """
        列出全部表元数据

        :param keyword: 表名/注释关键字过滤
        :return: 表清单响应
        """
        return TableListResponse(items=self.dao.list_tables(keyword))

    def get_table(self, table_name: str) -> TableDetail:
        """
        获取单表元数据

        :param table_name: 表名
        :return: 表详情
        :raises NotFoundError: 表不存在
        """
        return self.dao.get_table(table_name)

    # ############################### 字段建议 ###############################
    async def suggest(self, request: SuggestRequest) -> SuggestResponse:
        """
        生成字段配置建议(可选 AI 辅助, 任何 AI 异常都回退启发式规则)

        :param request: 建议请求
        :return: 命名/页面标题/字段配置/AI 是否生效
        """
        detail = self.dao.get_table(request.table_name)
        derived = derive_names(detail.name)
        warnings: list[str] = []

        # 模块名/类名以请求体为准, 非法值回退推导结果
        module_name = sanitize_snake(request.module_name) if request.module_name else ""
        if request.module_name and not module_name:
            warnings.append(f"模块名 {request.module_name!r} 不合法, 已回退推导值")
        module_name = module_name or derived.module_name

        class_name = sanitize_pascal(request.class_name) if request.class_name else ""
        if request.class_name and not class_name:
            warnings.append(f"类名 {request.class_name!r} 不合法, 已回退推导值")
        class_name = class_name or derived.class_name

        prefix_note = f"由表 {detail.name} 推导: 模块名 {derived.module_name}"
        if derived.removed_prefix:
            prefix_note += f"(已去除公共前缀 {derived.removed_prefix})"
        prefix_note += f", 类名 {derived.class_name}"
        warnings.append(prefix_note)
        if request.module_name or request.class_name:
            warnings.append(f"最终采用请求指定命名: 模块 {module_name}, 类 {class_name}")

        page_title = (detail.comment or "").strip() or class_name
        columns = [self._heuristic_column(meta) for meta in detail.columns]
        ai_used = False

        if request.use_ai:
            try:
                payload = await asyncio.wait_for(
                    self._ai_suggest(detail, columns, page_title), timeout=_AI_TIMEOUT
                )
                module_name, class_name, page_title, columns = self._apply_ai_payload(
                    payload, columns, module_name, class_name, page_title
                )
                ai_used = True
            except TimeoutError:
                logger.warning("代码生成器 AI 辅助超时(表 %s)", detail.name)
                warnings.append(f"AI 辅助超时({_AI_TIMEOUT}s), 已回退启发式规则")
            except Exception as e:  # noqa: BLE001 - AI 失败必须兜底, 不影响整个请求
                logger.warning("代码生成器 AI 辅助失败(表 %s): %s", detail.name, e)
                warnings.append(f"AI 辅助不可用, 已回退启发式规则: {str(e)[:200]}")

        return SuggestResponse(
            module_name=module_name,
            class_name=class_name,
            page_title=page_title,
            columns=columns,
            warnings=warnings,
            ai_used=ai_used,
        )

    def _heuristic_column(self, meta: ColumnMeta) -> ColumnSuggestion:
        """
        按字段类型/名称/注释推断控件与展示配置

        :param meta: 字段元数据
        :return: 字段建议
        """
        name = meta.name
        label = (meta.comment or name).strip()
        control = self._guess_control(meta)
        audit = name in _AUDIT_COLUMNS
        required = (
            not meta.nullable
            and meta.default is None
            and not meta.primary_key
            and not audit
        )
        searchable = (
            meta.type == "str"
            and not meta.primary_key
            and not audit
            and control in ("input", "select")
            and (meta.max_length is None or meta.max_length <= 255)
        )
        listable = not (meta.type in ("json", "bytes") or control == "textarea")
        editable = not meta.primary_key and not audit
        return ColumnSuggestion(
            name=name,
            label=label,
            control=control,
            required=required,
            searchable=searchable,
            listable=listable,
            editable=editable,
            dict_type=None,
            description=meta.comment or "",
            width=self._guess_width(control, label),
        )

    @staticmethod
    def _guess_control(meta: ColumnMeta) -> str:
        """
        由字段类型/名称推断控件类型

        :param meta: 字段元数据
        :return: 控件类型
        """
        py_type = meta.type
        if py_type == "bool":
            return "switch"
        if py_type in ("int", "float"):
            return "number"
        if py_type == "datetime":
            return "datetime"
        if py_type == "date":
            return "date"
        if py_type == "json":
            return "textarea"
        name = meta.name.lower()
        if name.endswith("_id") or name in {"id", "uuid", "code"}:
            return "input"
        if name in {
            "content",
            "description",
            "remark",
            "summary",
            "note",
            "comment",
            "address",
            "detail",
        } or (meta.max_length or 0) > 500:
            return "textarea"
        if name.endswith(("status", "type", "level", "kind", "category")):
            return "select"
        return "input"

    @staticmethod
    def _guess_width(control: str, label: str) -> int:
        """按控件与标签长度估算列表列宽"""
        if control == "switch":
            return 90
        if control in ("date", "datetime"):
            return 170
        if control == "number":
            return 120
        if control == "textarea":
            return 220
        return max(120, min(240, len(label) * 14 + 60))

    async def _ai_suggest(
        self,
        detail: TableDetail,
        columns: list[ColumnSuggestion],
        page_title: str,
    ) -> dict:
        """
        调用 module_ai 文本生成能力返回 JSON 建议

        :param detail: 表详情
        :param columns: 启发式字段建议(作为提示词输入)
        :param page_title: 当前页面标题
        :return: 解析后的 JSON 对象
        :raises Exception: 无可用模型/调用失败/非法 JSON
        """
        # 延迟导入: 避免代码生成器基础功能被 AI 依赖拖慢/阻断
        from module_ai.do.llm import ChatRequest
        from module_ai.service.llm import LLMService

        llm_service = LLMService()
        config = await llm_service.model_config_service.model_config_dao.get_first_by_type(
            "chat"
        )
        if config is None:
            raise RuntimeError("未配置可用的 chat 模型")

        table_payload = {
            "table_name": detail.name,
            "table_comment": detail.comment,
            "page_title": page_title,
            "columns": [
                {
                    "name": col.name,
                    "type": meta.type,
                    "nullable": meta.nullable,
                    "primary_key": meta.primary_key,
                    "max_length": meta.max_length,
                    "comment": meta.comment,
                    "current_control": col.control,
                }
                for col, meta in zip(columns, detail.columns, strict=False)
            ],
        }
        request = ChatRequest(
            model_id=config.id,
            messages=[
                {"role": "system", "content": _AI_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(table_payload, ensure_ascii=False),
                },
            ],
            streaming=False,
        )
        result = await llm_service.chat_completion(request)
        return _parse_json_object(_content_text(result))

    def _apply_ai_payload(
        self,
        payload: dict,
        columns: list[ColumnSuggestion],
        module_name: str,
        class_name: str,
        page_title: str,
    ) -> tuple[str, str, str, list[ColumnSuggestion]]:
        """
        合并 AI 建议(只采纳合法值, 未知字段忽略)

        :param payload: AI 返回的 JSON 对象
        :param columns: 启发式字段建议
        :param module_name: 当前模块名
        :param class_name: 当前类名
        :param page_title: 当前页面标题
        :return: (模块名, 类名, 页面标题, 合并后的字段建议)
        """
        if not any(
            key in payload
            for key in ("module_name", "class_name", "page_title", "columns")
        ):
            raise ValueError("AI 返回内容为空")

        ai_module = sanitize_snake(str(payload.get("module_name") or ""))
        if ai_module:
            module_name = ai_module
        ai_class = sanitize_pascal(str(payload.get("class_name") or ""))
        if ai_class:
            class_name = ai_class
        ai_title = str(payload.get("page_title") or "").strip()
        if ai_title:
            page_title = ai_title

        raw_columns = payload.get("columns")
        if not isinstance(raw_columns, list):
            raise ValueError("AI 返回的 columns 不是数组")

        index_by_name = {col.name: i for i, col in enumerate(columns)}
        for item in raw_columns:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            index = index_by_name.get(name)
            if index is None:
                continue
            updates: dict = {}
            label = str(item.get("label") or "").strip()
            if label:
                updates["label"] = label
            control = str(item.get("control") or "").strip().lower()
            if control in _CONTROL_VALUES:
                updates["control"] = control
            for key in ("searchable", "listable", "editable"):
                value = _as_bool(item.get(key))
                if value is not None:
                    updates[key] = value
            width = _as_int(item.get("width"))
            if width is not None:
                updates["width"] = max(60, min(400, width))
            if "dict_type" in item:
                dict_type = item.get("dict_type")
                updates["dict_type"] = str(dict_type) if dict_type else None
            if updates:
                columns[index] = columns[index].model_copy(update=updates)
        return module_name, class_name, page_title, columns

    # ############################### 预览 / 生成 ###############################
    def preview(self, request: PreviewRequest) -> PreviewResponse:
        """
        渲染代码但不写盘

        :param request: 预览请求
        :return: 文件内容/是否存在/提示
        """
        outputs, warnings = self._build_outputs(request)
        files: list[GeneratedFile] = []
        for output in outputs:
            target = self._safe_path(output.path)
            files.append(
                GeneratedFile(
                    path=self._display_path(target),
                    language=output.language,
                    content=output.content,
                    exists=target.is_file(),
                )
            )
        return PreviewResponse(files=files, warnings=warnings)

    def generate(self, request: GenerateRequest) -> GenerateResponse:
        """
        渲染并写盘(仅允许 src 根目录内, overwrite=false 时跳过已存在文件)

        :param request: 生成请求
        :return: 已写入/已跳过文件与提示
        """
        outputs, warnings = self._build_outputs(request)
        written: list[str] = []
        skipped: list[str] = []
        for output in outputs:
            target = self._safe_path(output.path)
            display = self._display_path(target)
            if target.is_file() and not request.overwrite:
                skipped.append(display)
                warnings.append(f"已存在跳过: {display}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output.content, encoding="utf-8")
            written.append(display)
        self._ensure_package_inits(outputs)
        return GenerateResponse(written=written, skipped=skipped, warnings=warnings)

    @staticmethod
    def _ensure_package_inits(outputs: list[_Output]) -> None:
        """
        为新生成的后端模块补齐包声明文件(不进入预览列表, 幂等)

        生成目标落在 ``src/module_<name>/`` 下, 首次生成时该模块目录尚不存在,
        缺少 ``__init__.py`` 会导致导入链路与现有模块不一致, 故按层静默补齐。

        :param outputs: 已写入的待生成文件列表
        """
        for output in outputs:
            parent = output.path.parent
            if parent.parent.name.startswith("module_") and parent.name in _LAYER_DIRS:
                for directory in (parent.parent, parent):
                    init_file = directory / "__init__.py"
                    if not init_file.is_file():
                        init_file.write_text("", encoding="utf-8")

    def _build_outputs(
        self, request: PreviewRequest
    ) -> tuple[list[_Output], list[str]]:
        """
        组装全部待生成文件与提示

        :param request: 预览/生成请求
        :return: (文件列表, 提示列表)
        """
        detail = self.dao.get_table(request.table_name)
        derived = derive_names(detail.name)
        module_name = sanitize_snake(request.module_name) or derived.module_name
        class_name = (
            sanitize_pascal(request.class_name)
            or sanitize_pascal(module_name)
            or derived.class_name
        )
        page_title = (request.page_title or "").strip() or (
            (detail.comment or "").strip() or class_name
        )

        context, context_warnings = self._build_context(
            request, detail, module_name, class_name, page_title
        )
        warnings: list[str] = [*context_warnings, *self._runtime_warnings(module_name)]
        outputs: list[_Output] = []

        module_dir = _SRC_ROOT / f"module_{module_name}"
        if request.include_backend:
            if (module_dir / "do" / f"{module_name}.py").is_file():
                warnings.append(
                    "已存在同名 do 模型文件, 请合并字段或调整 __tablename__, "
                    "避免 SQLModel 重复注册同一张表"
                )
            outputs.extend(
                [
                    self._make_output(
                        module_dir / "do" / f"{module_name}.py",
                        "python",
                        "backend_do.py.j2",
                        context,
                    ),
                    self._make_output(
                        module_dir / "dao" / f"{module_name}.py",
                        "python",
                        "backend_dao.py.j2",
                        context,
                    ),
                    self._make_output(
                        module_dir / "service" / f"{module_name}.py",
                        "python",
                        "backend_service.py.j2",
                        context,
                    ),
                    self._make_output(
                        module_dir / "controller" / f"{module_name}.py",
                        "python",
                        "backend_controller.py.j2",
                        context,
                    ),
                    self._make_output(
                        module_dir / "dependencies" / f"{module_name}.py",
                        "python",
                        "backend_dependencies.py.j2",
                        context,
                    ),
                ]
            )

        if request.include_frontend:
            front_mod = _FRONTEND_SRC_ROOT / "modules" / module_name
            outputs.extend(
                [
                    self._make_output(
                        front_mod / "types" / f"{module_name}.ts",
                        "typescript",
                        "frontend_types.ts.j2",
                        context,
                    ),
                    self._make_output(
                        front_mod / "api" / f"{module_name}.ts",
                        "typescript",
                        "frontend_api.ts.j2",
                        context,
                    ),
                    self._make_output(
                        front_mod / "pages" / f"{module_name}.vue",
                        "vue",
                        "frontend_page.vue.j2",
                        context,
                    ),
                ]
            )

        if not outputs:
            warnings.append("未选择任何生成内容(include_backend/include_frontend 均为 false)")
        return outputs, warnings

    @staticmethod
    def _make_output(
        path: Path, language: str, template: str, context: dict
    ) -> _Output:
        """渲染单个模板为待写文件"""
        return _Output(path=path, language=language, content=render(template, context))

    # ############################### 上下文构建 ###############################
    def _build_context(
        self,
        request: PreviewRequest,
        detail: TableDetail,
        module_name: str,
        class_name: str,
        page_title: str,
    ) -> tuple[dict, list[str]]:
        """
        构建模板上下文(字段配置合并 + Python/TS 类型与表单默认值推导)

        :param request: 预览请求
        :param detail: 表详情
        :param module_name: 模块名
        :param class_name: 类名
        :param page_title: 页面标题
        :return: (模板上下文, 提示列表)
        """
        warnings: list[str] = []
        suggestion_map = {col.name: col for col in request.columns}
        table_names = {meta.name for meta in detail.columns}
        unknown = [name for name in suggestion_map if name not in table_names]
        if unknown:
            warnings.append(f"已忽略请求中不存在的字段: {', '.join(sorted(unknown))}")

        columns: list[dict] = []
        for meta in detail.columns:
            suggestion = suggestion_map.get(meta.name) or self._heuristic_column(meta)
            columns.append(
                self._enrich_column(
                    meta,
                    suggestion,
                )
            )

        pk_columns = [col for col in columns if col["primary_key"]]
        if len(pk_columns) > 1:
            warnings.append(
                "检测到复合主键, 生成代码仅以第一个主键作为主键字段, 请按需手工调整"
            )
        if not pk_columns:
            warnings.append("表未声明主键, 已生成 id 字符串主键, 请按实际表结构调整")
            columns.insert(
                0,
                self._enrich_column(
                    ColumnMeta(
                        name="id",
                        type="str",
                        sql_type="VARCHAR(32)",
                        nullable=False,
                        primary_key=True,
                        default=None,
                        comment="唯一标识符",
                        max_length=32,
                    ),
                    ColumnSuggestion(
                        name="id",
                        label="唯一标识符",
                        control="input",
                        required=True,
                        searchable=False,
                        listable=True,
                        editable=False,
                        description="唯一标识符",
                        width=180,
                    ),
                ),
            )
            pk_columns = [columns[0]]

        # 表模型字段(排除主键与审计字段, 审计字段单独定义默认值)
        base_fields = [
            col
            for col in columns
            if not col["primary_key"] and not col["audit"]
        ]
        for col in base_fields:
            # 基础模型与更新模型各自持有声明文本, 避免互相覆盖
            col["base_declaration"] = self._base_field_declaration(col)
            col["update_declaration"] = self._update_field_declaration(col)
        update_fields = base_fields

        pk_field = pk_columns[0]
        pk_declaration = self._pk_field_declaration(pk_field)
        pk_name = pk_field["name"]
        id_py_type = "int" if pk_field["py_type"] == "int" else "str"
        id_ts_type = "number" if id_py_type == "int" else "string"

        has_created_at = any(col["name"] == "created_at" for col in columns)
        has_updated_at = any(col["name"] == "updated_at" for col in columns)

        # 查询字段: 优先 searchable 字符串字段, 最多两个
        keyword_columns = [
            col["name"]
            for col in columns
            if col["searchable"] and col["py_type"] == "str" and not col["primary_key"]
        ][:2]
        if not keyword_columns:
            fallback = next(
                (
                    col["name"]
                    for col in columns
                    if col["py_type"] == "str" and not col["primary_key"]
                ),
                None,
            )
            if fallback:
                keyword_columns = [fallback]
        keyword_condition = " | ".join(
            f"({class_name}.{name}.contains(keyword))" for name in keyword_columns
        )

        order_clause = (
            f"{class_name}.created_at.desc()"
            if has_created_at
            else f"{class_name}.{pk_name}.desc()"
        )

        list_columns = [col for col in columns if col["listable"]] or columns[:4]
        form_columns = [
            col
            for col in columns
            if (col["editable"] or col["required"])
            and not col["primary_key"]
            and not col["audit"]
            and col["py_type"] not in ("json", "bytes")
        ]
        required_form_columns = [col for col in form_columns if col["required"]]

        # TS 类型分开计算, 避免污染 Python 注解
        for col in columns:
            col["ts_type"] = ts_type(col["py_type"], col["nullable"])
            col["ts_optional"] = False
        create_ts_fields = []
        for col in base_fields:
            create_ts_fields.append(
                {
                    "name": col["name"],
                    # 创建表单不承载 null, 可空字段以"可选 + 非空类型"表达
                    "ts_type": ts_type(col["py_type"], False),
                    "optional": not col["required"],
                }
            )

        for col in form_columns:
            default = self._form_default(col)
            col["form_default"] = default
            # 编辑回填: 可空字段用默认值兜底, 避免 Element Plus 组件收到 null
            col["edit_expr"] = (
                f"row.{col['name']} ?? {default}"
                if col["nullable"]
                else f"row.{col['name']}"
            )

        context = {
            "table_name": detail.name,
            "table_comment": detail.comment or "",
            "module_name": module_name,
            "module_package": f"module_{module_name}",
            "class_name": class_name,
            "route_prefix": f"/{pluralize(module_name)}",
            "page_title": page_title,
            "seal": page_title[:1] or "生",
            "sub_title": (detail.comment or page_title).strip(),
            "columns": columns,
            "list_columns": list_columns,
            "form_columns": form_columns,
            "required_form_columns": required_form_columns,
            "base_fields": base_fields,
            "update_fields": update_fields,
            "pk_fields": [
                {
                    **pk_field,
                    "declaration": pk_declaration,
                }
            ],
            "pk_name": pk_name,
            "id_py_type": id_py_type,
            "id_ts_type": id_ts_type,
            "has_created_at": has_created_at,
            "has_updated_at": has_updated_at,
            "keyword_columns": keyword_columns,
            "keyword_condition": keyword_condition,
            "order_clause": order_clause,
            "create_ts_fields": create_ts_fields,
        }
        return context, warnings

    def _enrich_column(
        self, meta: ColumnMeta, suggestion: ColumnSuggestion
    ) -> dict:
        """
        合并字段元数据与建议, 生成模板可用的完整字段描述

        :param meta: 字段元数据
        :param suggestion: 字段建议
        :return: 字段字典(含 Py/TS 类型、是否审计字段等)
        """
        width = max(60, min(400, int(suggestion.width or 160)))
        return {
            "name": meta.name,
            "label": (suggestion.label or meta.comment or meta.name).strip(),
            "control": (
                suggestion.control
                if suggestion.control in _CONTROL_VALUES
                else "input"
            ),
            "required": bool(suggestion.required),
            "searchable": bool(suggestion.searchable),
            "listable": bool(suggestion.listable),
            "editable": bool(suggestion.editable),
            "dict_type": suggestion.dict_type,
            "description": (suggestion.description or meta.comment or "").strip(),
            "width": width,
            "py_type": meta.type,
            "nullable": meta.nullable,
            "primary_key": meta.primary_key,
            "max_length": meta.max_length,
            "db_default": meta.default,
            "comment": meta.comment,
            "audit": meta.name in _AUDIT_COLUMNS,
        }

    @staticmethod
    def _base_field_declaration(col: dict) -> str:
        """生成基础模型字段声明"""
        args: list[str] = []
        if col["nullable"]:
            args.append("default=None")
        else:
            literal = _default_literal(col)
            if literal is not None:
                args.append(f"default={literal}")
            elif col["py_type"] == "json":
                # JSON 字段前端表单不直接编辑, 给空对象默认值以保证创建请求可用
                args.append("default_factory=dict")
            elif col["py_type"] == "bytes":
                args.append("default_factory=bytes")
        if col["py_type"] == "str" and col["max_length"]:
            args.append(f"max_length={col['max_length']}")
        description = col["comment"] or col["label"]
        if description:
            args.append(f"description={py_literal(description)}")
        annotation = python_annotation(col["py_type"], col["nullable"])
        return f"{col['name']}: {annotation} = Field({', '.join(args)})"

    @staticmethod
    def _update_field_declaration(col: dict) -> str:
        """生成更新请求模型字段声明(全部可选)"""
        args = ["default=None"]
        if col["py_type"] == "str" and col["max_length"]:
            args.append(f"max_length={col['max_length']}")
        description = col["comment"] or col["label"]
        if description:
            args.append(f"description={py_literal(description)}")
        annotation = python_annotation(col["py_type"], True)
        return f"{col['name']}: {annotation} = Field({', '.join(args)})"

    @staticmethod
    def _pk_field_declaration(col: dict) -> str:
        """生成主键字段声明(字符串主键用 uuid 默认值, 整型主键自增)"""
        name = col["name"]
        description = py_literal(col["comment"] or col["label"] or "唯一标识符")
        if col["py_type"] == "int":
            return (
                f"{name}: int | None = Field(default=None, primary_key=True, "
                f"index=True, description={description})"
            )
        return (
            f"{name}: str = Field(default_factory=lambda: uuid4().hex, "
            f"primary_key=True, index=True, description={description})"
        )

    @staticmethod
    def _form_default(col: dict) -> str:
        """前端表单初始值(TS 字面量)"""
        if col["py_type"] == "bool":
            return "false"
        if col["py_type"] in ("int", "float"):
            return "0"
        if col["py_type"] in ("json", "bytes"):
            return "null"
        return "''"

    @staticmethod
    def _runtime_warnings(module_name: str) -> list[str]:
        """
        生成器不会自动修改共享文件, 以提示形式告知需要人工补齐的注册/权限

        :param module_name: 模块名
        :return: 提示列表
        """
        return [
            f"需在 src/app.py 追加: from module_{module_name}.controller import {module_name}  # noqa: F401",
            (
                "需在权限声明(module_authorization/config/permissions.py)新增权限码: "
                f"sys:{module_name}:read / sys:{module_name}:create / "
                f"sys:{module_name}:update / sys:{module_name}:delete"
            ),
            f"前端菜单需在 src/app/config/menu.ts 注册页面路由 /{module_name}",
            "生成代码为脚手架, 合入前请按业务补充校验、关联查询与索引说明",
        ]

    # ############################### 路径安全 ###############################
    @staticmethod
    def _safe_path(path: Path) -> Path:
        """
        解析并校验绝对路径, 只允许落在后端 src 或前端 src 根之内

        :param path: 目标路径
        :return: 解析后的绝对路径
        :raises ValueError: 路径越界(目录穿越)
        """
        resolved = path.resolve()
        for root in (_SRC_ROOT.resolve(), _FRONTEND_SRC_ROOT.resolve()):
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise ValueError(f"拒绝写入越界路径: {path}")

    @staticmethod
    def _display_path(path: Path) -> str:
        """转为仓库根相对路径(便于前端展示, 不泄露本机绝对路径)"""
        try:
            return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def _default_literal(col: dict) -> str | None:
    """
    数据库默认值转 Python 字面量(日期/JSON 等复杂默认值不展开)

    :param col: 字段字典
    :return: 字面量文本, 无法安全表达时返回 None
    """
    text = col["db_default"]
    if text is None:
        return None
    py_type = col["py_type"]
    if py_type == "bool":
        lowered = str(text).strip().lower()
        if lowered in ("true", "t", "1", "yes"):
            return "True"
        if lowered in ("false", "f", "0", "no"):
            return "False"
        return None
    if py_type in ("int", "float"):
        try:
            return str(int(text)) if py_type == "int" else str(float(text))
        except (TypeError, ValueError):
            return None
    if py_type == "str":
        return py_literal(str(text))
    return None


def _as_bool(value) -> bool | None:
    """把 AI 返回值宽松转换为布尔(无法判断时返回 None)"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    return None


def _as_int(value) -> int | None:
    """把 AI 返回值转换为整数(非法值返回 None)"""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _content_text(result) -> str:
    """提取 LLM 响应文本(兼容 str / 分片列表两种 content 形态)"""
    content = getattr(result, "content", result)
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content or "")


def _parse_json_object(text: str) -> dict:
    """
    从模型输出中提取 JSON 对象(容忍 markdown 代码块与前后解释文字)

    :param text: 模型原始输出
    :return: 解析后的字典
    :raises ValueError: 输出中不存在合法 JSON 对象
    """
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("AI 未返回合法 JSON")
