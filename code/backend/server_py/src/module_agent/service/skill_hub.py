"""Skill Hub: 社区 SKILL.md 渐进式包加载器(REQ-018 批次 3, W-14)

设计落点(04 设计文档 §3.5): 外部能力不新增第四层、不绕过 SkillRuntime——
包由加载器**拆解翻译**为标准 Skill 进统一注册表:

    SKILL.md(frontmatter + 指令正文) → pack.{包名}.main   prompt Skill(模型执行, 渐进式披露)
    scripts/*.{py,sh,js}              → pack.{包名}.{名}  script 沙箱 Skill(默认不暴露对话)
    references/*                      → 知识资产(不单独成 Skill, 清单注入指令模板尾部)

- 包内容全量存 ai_skill_version.manifest_snapshot(纯文本资产, 无文件系统状态;
  沙箱执行时落一次性临时目录) —— 与内置 Skill 同表同治, origin=external
- 加载器只做声明翻译不做语义改写; 治理(沙箱边界/副作用声明)按契约校验与
  沙箱测试把关(§3.5 约定)
"""

import io
import logging
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any

from sqlmodel import select

from common.config.db import db_manager
from common.utils.fastapi_ex.exceptions import BusinessError, NotFoundError
from module_agent.do.skill import AiSkill, AiSkillVersion, SkillPublishStatus
from module_agent.skills.manifest import (
    ExecutionSpec,
    IdempotencySpec,
    RetrySpec,
    SkillManifest,
)
from module_agent.skills.registry import SKILL_REGISTRY, register_skill

logger = logging.getLogger(__name__)

# 包边界
MAX_PACKAGE_BYTES = 10 * 1024 * 1024        # zip 解压后总量 10MB
MAX_SCRIPT_PER_PACKAGE = 20
_SCRIPT_LANG_BY_EXT = {".py": "python", ".sh": "bash", ".js": "node"}
_PACKAGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """解析 SKILL.md: YAML frontmatter + 指令正文"""
    import yaml

    match = _FRONTMATTER_PATTERN.match(content.strip())
    if match is None:
        raise BusinessError("SKILL.md 缺少 frontmatter(应以 '---' 开始的 YAML 头)")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise BusinessError(f"SKILL.md frontmatter YAML 解析失败: {e}") from e
    if not isinstance(meta, dict):
        raise BusinessError("SKILL.md frontmatter 必须是 YAML 对象")
    instructions = match.group(2).strip()
    if not instructions:
        raise BusinessError("SKILL.md 指令正文为空")
    return meta, instructions


def _safe_extract(zip_bytes: bytes) -> dict[str, str]:
    """解压 zip 为 {相对路径: 文本内容}(路径穿越防护 + 边界限制; 仅收文本文件)"""
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise BusinessError(f"非法 zip 包: {e}") from e
    files: dict[str, str] = {}
    total = 0
    for info in archive.infolist():
        name = PurePosixPath(info.filename)
        if info.is_dir() or name.is_absolute() or ".." in name.parts:
            continue
        rel = name.as_posix()
        if rel not in ("SKILL.md",) and not (
            rel.startswith("scripts/") or rel.startswith("references/")
        ):
            continue  # 只收约定目录(其余忽略, 防夹带)
        total += info.file_size
        if total > MAX_PACKAGE_BYTES:
            raise BusinessError(f"包内容超过 {MAX_PACKAGE_BYTES // 1024 // 1024}MB 上限")
        try:
            files[rel] = archive.read(info).decode("utf-8")
        except UnicodeDecodeError as e:
            raise BusinessError(f"包内仅允许 UTF-8 文本文件: {rel}") from e
    if "SKILL.md" not in files:
        raise BusinessError("包根目录缺少 SKILL.md")
    return files


def _build_package_manifests(
    package_name: str, files: dict[str, str]
) -> tuple[SkillManifest, dict[str, SkillManifest], dict[str, str]]:
    """拆解包为 Manifest 集合: (main prompt, {脚本名: script manifest}, references)"""
    meta, instructions = parse_skill_md(files["SKILL.md"])
    name = str(meta.get("name") or package_name)
    version = str(meta.get("version") or "1")
    description = str(meta.get("description") or f"社区 Skill 包 {name}")

    references = {k: v for k, v in files.items() if k.startswith("references/")}
    scripts = {k: v for k, v in files.items() if k.startswith("scripts/")}
    if len(scripts) > MAX_SCRIPT_PER_PACKAGE:
        raise BusinessError(f"脚本数量超过上限 {MAX_SCRIPT_PER_PACKAGE}")

    # 渐进式披露: references 清单注入指令尾部(模型按需向用户索取内容)
    template = instructions
    if references:
        listing = "\n".join(f"- {rel}" for rel in sorted(references))
        template += (
            "\n\n---\n你可以引用以下参考资料(渐进式披露: 需要时再请用户提供对应内容):\n"
            + listing
        )

    main = SkillManifest(
        namespace=f"pack.{package_name}",
        key="main",
        name=name,
        description=description,
        skill_type="prompt",
        nature="ai",
        impl_ref=f"skill_hub:pack.{package_name}.main",
        version=version,
        input_schema={
            "type": "object",
            "required": ["input"],
            "properties": {"input": {"type": "string", "description": "任务/问题(注入指令模板)"}},
        },
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        required_capabilities=["chat"],
        execution=ExecutionSpec(modes=["inline", "queued"], inline_timeout_s=120),
        idempotency=IdempotencySpec(keys=[]),
        retry=RetrySpec(max=0),
        side_effects="none",
        agent_callable=True,
        prompt={"template": template, "output_format": "text", "origin": "skill_hub"},
    )

    script_manifests: dict[str, SkillManifest] = {}
    for rel, code in sorted(scripts.items()):
        stem = PurePosixPath(rel).stem
        language = _SCRIPT_LANG_BY_EXT.get(PurePosixPath(rel).suffix)
        if language is None:
            raise BusinessError(f"不支持的脚本类型: {rel}(可选 {sorted(set(_SCRIPT_LANG_BY_EXT.values()))})")
        script_manifests[stem] = SkillManifest(
            namespace=f"pack.{package_name}",
            key=stem,
            name=f"{name} · {stem}",
            description=str(meta.get(f"script_{stem}_description") or f"包 {name} 的 {stem} 脚本(沙箱执行)"),
            skill_type="python_script" if language == "python" else "script",
            nature="static",
            impl_ref=f"skill_hub:pack.{package_name}.{stem}",
            version=version,
            input_schema={
                "type": "object",
                "required": ["input"],
                "properties": {"input": {"type": "string", "description": "脚本文本输入"}},
            },
            output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            execution=ExecutionSpec(modes=["inline"], inline_timeout_s=60),
            idempotency=IdempotencySpec(keys=[]),
            retry=RetrySpec(max=0),
            # 脚本副作用边界仅沙箱声明, 默认不暴露给对话(管理员可改 DB 注册表后重启)
            side_effects="external",
            agent_callable=False,
            script={"language": language, "code": code, "origin": f"skill_hub:{package_name}"},
        )
    return main, script_manifests, references


def _register_external(manifest: SkillManifest) -> None:
    """注册外部 Skill(按类型分派内建执行器闭包, 与 prompt/builtin 同一 load_impl 路径)"""
    from module_agent.service import skill_runtime as sr
    from module_agent.service.prompt_skill import make_prompt_runner
    from module_agent.service.script_sandbox import make_script_runner

    register_skill(manifest)
    if manifest.skill_type == "prompt":
        sr._impl_cache[manifest.impl_ref] = make_prompt_runner(manifest)
    elif manifest.skill_type in ("python_script", "script"):
        sr._impl_cache[manifest.impl_ref] = make_script_runner(manifest)
    else:
        raise BusinessError(f"外部包不支持拆解为 {manifest.skill_type} 类型")


def _unregister(uid: str) -> None:
    from module_agent.service import skill_runtime as sr

    manifest = SKILL_REGISTRY.pop(uid, None)
    if manifest is not None:
        sr._impl_cache.pop(manifest.impl_ref, None)


class SkillHubService:
    """社区包导入/清单/删除(拆解注册同表同治)"""

    async def import_package(self, zip_bytes: bytes, user_id: str) -> dict:
        files = _safe_extract(zip_bytes)
        meta, _ = parse_skill_md(files["SKILL.md"])
        raw_name = str(meta.get("name") or "")
        if not _PACKAGE_NAME_PATTERN.match(raw_name or ""):
            raise BusinessError(f"包名非法(小写字母/数字/下划线, 2-41 字符): {raw_name!r}")
        package_name = raw_name
        namespace = f"pack.{package_name}"
        if await self._namespace_exists(namespace):
            raise BusinessError(f"包已存在: {namespace}(先删除旧版再导入)")

        main, script_manifests, references = _build_package_manifests(package_name, files)
        # 校验全部通过后再注册/落库(失败不留半成品)
        for m in [main, *script_manifests.values()]:
            m.check_invariants()

        package_payload = {
            "skill_md": files["SKILL.md"],
            "scripts": {k: v for k, v in files.items() if k.startswith("scripts/")},
            "references": references,
            "files": sorted(files),
        }
        async with db_manager.db_rel.session_factory() as session:
            rows: list[AiSkill] = []
            version = main.version
            # 主行(包登记) + main Skill 行 + 脚本行
            entries: list[tuple[str, str, str, str, dict]] = [
                (main.uid, "main", main.name, "prompt", main.model_dump(mode="json")),
                *(
                    (m.uid, m.key, m.name, m.skill_type, m.model_dump(mode="json"))
                    for m in script_manifests.values()
                ),
            ]
            for key, _sub, name, skill_type, snapshot in entries:
                snapshot = dict(snapshot)
                snapshot["_package"] = package_payload
                import hashlib
                import json as _json

                config_hash = hashlib.sha256(
                    _json.dumps(
                        {k: snapshot.get(k) for k in ("key", "skill_type", "prompt", "script", "version")},
                        ensure_ascii=False, sort_keys=True,
                    ).encode()
                ).hexdigest()
                row = AiSkill(
                    key=key, namespace=namespace, name=name,
                    description=main.description, category="action",
                    skill_type=skill_type, nature="ai" if skill_type == "prompt" else "static",
                    origin="external", origin_version=version,
                    owner_user_id=user_id,
                    current_version=version, status=SkillPublishStatus.PUBLISHED,
                )
                session.add(row)
                await session.flush()
                session.add(
                    AiSkillVersion(
                        skill_id=row.id, version=version,
                        config_hash=config_hash,
                        manifest_snapshot=snapshot,
                    )
                )
                rows.append(row)
            await session.commit()

        # 注册生效
        _register_external(main)
        for m in script_manifests.values():
            _register_external(m)
        return {
            "namespace": namespace,
            "version": version,
            "skills": [main.uid] + [m.uid for m in script_manifests.values()],
            "references": sorted(references),
            "skill_ids": [r.id for r in rows],
        }

    async def list_packages(self) -> list[dict]:
        async with db_manager.db_rel.session_factory() as session:
            rows = (
                await session.exec(
                    select(AiSkill).where(
                        AiSkill.origin == "external", AiSkill.namespace.like("pack.%")
                    )
                )
            ).all()
        packages: dict[str, dict] = {}
        for r in rows:
            pkg = packages.setdefault(
                r.namespace,
                {
                    "namespace": r.namespace,
                    "name": r.name,
                    "version": r.origin_version,
                    "status": r.status,
                    "owner_user_id": r.owner_user_id,
                    "skills": [],
                },
            )
            pkg["skills"].append({"key": r.key, "skill_type": r.skill_type, "registered": r.key in SKILL_REGISTRY or f"{r.namespace}.{r.key}" in SKILL_REGISTRY})
        return sorted(packages.values(), key=lambda p: p["namespace"])

    async def _namespace_exists(self, namespace: str) -> bool:
        async with db_manager.db_rel.session_factory() as session:
            row = (
                await session.exec(
                    select(AiSkill).where(AiSkill.namespace == namespace).limit(1)
                )
            ).first()
            return row is not None

    async def remove_package(self, namespace: str, user_id: str) -> dict:
        if not namespace.startswith("pack."):
            raise BusinessError(f"非法包命名空间: {namespace}")
        async with db_manager.db_rel.session_factory() as session:
            rows = (
                await session.exec(select(AiSkill).where(AiSkill.namespace == namespace))
            ).all()
            if not rows:
                raise NotFoundError(f"包不存在: {namespace}")
            for row in rows:
                _unregister(row.key)
                row.status = SkillPublishStatus.DEPRECATED
                row.deprecated = True
            await session.commit()
        return {"namespace": namespace, "status": "deprecated"}


async def restore_skill_hub_packages() -> dict:
    """启动恢复: 从 DB 重建外部包注册(读 manifest_snapshot, 无需原始 zip)"""
    restored = 0
    async with db_manager.db_rel.session_factory() as session:
        rows = (
            await session.exec(
                select(AiSkill).where(
                    AiSkill.origin == "external",
                    AiSkill.status == SkillPublishStatus.PUBLISHED,
                    AiSkill.namespace.like("pack.%"),
                )
            )
        ).all()
        snapshots: list[dict] = []
        for row in rows:
            latest = (
                await session.exec(
                    select(AiSkillVersion)
                    .where(AiSkillVersion.skill_id == row.id)
                    .order_by(AiSkillVersion.created_at.desc())
                    .limit(1)
                )
            ).first()
            if latest is not None:
                snapshots.append(dict(latest.manifest_snapshot or {}))
    for snapshot in snapshots:
        try:
            manifest = SkillManifest(**{k: v for k, v in snapshot.items() if not k.startswith("_")})
            _register_external(manifest)
            restored += 1
        except Exception as e:
            logger.warning("外部包 Skill 恢复失败: %s", e)
    logger.info("Skill Hub 包恢复完成: %s 个 Skill", restored)
    return {"restored": restored}
