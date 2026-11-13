"""script 沙箱执行器(REQ-018 批次 3, FEAT-AICAP-009)

skill_type ∈ {python_script, script} 的内建执行体:
- 隔离模型: 独立子进程 + 空环境变量(白名单放行) + 一次性临时工作目录 +
  硬超时杀进程 + 输出大小截断; 进程身份仍为宿主用户, 网络隔离依赖部署层
  (容器/命名空间), 沙箱测试(test_batch3_features.py)固化已声明边界
- I/O 约定: stdin = JSON(input); stdout 末行若可解析为 JSON object 则作为
  结构化结果, 否则整体作为 {"text": stdout}; 退出码非 0 → permanent 失败
- 与 prompt Skill 同模式: 注册时生成专属闭包注入 impl 缓存(load_impl 单一路径)
"""

import asyncio
import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 沙箱资源边界(批次 3 声明式边界; 部署层容器化后获得网络/文件系统强隔离)
MAX_OUTPUT_BYTES = 1024 * 1024      # stdout/stderr 合计上限 1MB
MAX_CODE_BYTES = 512 * 1024         # 脚本体上限 512KB
SANDBOX_TIMEOUT_S = 60              # 沙箱硬超时兜底(invoke timeout_s 之外的绝对上限)
# 环境白名单: 仅基础 locale/时区(PATH 由解释器定位需要)
_BASE_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "Asia/Shanghai"}

_INTERPRETERS: dict[str, list[str]] = {
    # python 用当前进程解释器绝对路径(社区包依赖平台环境安装的库, 如 defusedxml);
    # -s 隔离用户级 site、-E 忽略 PYTHON* 环境注入, 但保留脚本目录入 sys.path
    # (伴随模块树 office/ 等相对 import 的前提); 强隔离依赖部署层容器化
    "python": [__import__("sys").executable, "-s", "-E"],
    "bash": ["bash", "--noprofile", "--norc"],
    "node": ["node"],
}
_ENTRY_FILENAMES: dict[str, str] = {"python": "script.py", "bash": "script.sh", "node": "script.js"}


class SandboxViolationError(ValueError):
    """脚本声明/执行违反沙箱边界(非零退出码、超时、输出超限)"""


def _validate_language(language: str) -> None:
    if language not in _INTERPRETERS:
        raise SandboxViolationError(f"不支持的脚本语言: {language!r}(可选: {sorted(_INTERPRETERS)})")


async def execute_in_sandbox(
    language: str,
    code: str,
    skill_input: dict,
    *,
    env_allowed: list[str] | None = None,
    timeout_s: float | None = None,
    extra_files: dict[str, str] | None = None,
) -> dict:
    """在一次性沙箱目录中执行脚本并返回结果 dict

    :param code: 脚本内容(stdin 收 JSON input, 期望 stdout 输出结果)
    :param extra_files: 随脚本落盘的附加文件(Skill Hub 包内依赖脚本), 相对路径 → 内容
    :raises SandboxViolationError: 超时/非零退出/输出超限/语言不支持(permanent)
    """
    _validate_language(language)
    if len(code.encode()) > MAX_CODE_BYTES:
        raise SandboxViolationError(f"脚本过大(>{MAX_CODE_BYTES // 1024}KB)")

    with tempfile.TemporaryDirectory(prefix="skill_sandbox_") as sandbox_dir:
        entry = Path(sandbox_dir) / _ENTRY_FILENAMES[language]
        entry.write_text(code, encoding="utf-8")
        for rel, content in (extra_files or {}).items():
            # 路径穿越防护: 附加文件必须落在沙箱目录内
            target = (Path(sandbox_dir) / rel).resolve()
            if sandbox_dir not in str(target):
                raise SandboxViolationError(f"附加文件路径越界: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        env = dict(_BASE_ENV)
        import os

        for name in env_allowed or []:
            value = os.environ.get(name)
            if value is not None:
                env[name] = value  # 仅显式声明的变量放行(如 API 代理地址)

        cmd = [*_INTERPRETERS[language], entry.name]
        timeout = min(float(timeout_s or SANDBOX_TIMEOUT_S), SANDBOX_TIMEOUT_S)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=sandbox_dir,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise SandboxViolationError(f"沙箱解释器不可用({language}): {e}") from e
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(json.dumps(skill_input, ensure_ascii=False).encode()),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise SandboxViolationError(f"脚本执行超时(>{timeout:.0f}s), 已强制终止")

        if len(stdout) + len(stderr) > MAX_OUTPUT_BYTES:
            raise SandboxViolationError(f"脚本输出超限(>{MAX_OUTPUT_BYTES // 1024}KB)")
        stdout_text = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")

        if proc.returncode != 0:
            raise SandboxViolationError(
                f"脚本退出码 {proc.returncode}: {stderr_text.strip()[:500] or stdout_text.strip()[:500]}"
            )
        # stdout 末行 JSON object → 结构化结果; 否则整体文本
        lines = [line for line in stdout_text.strip().splitlines() if line.strip()]
        if lines:
            try:
                parsed = json.loads(lines[-1])
                if isinstance(parsed, dict):
                    result = parsed
                    if stderr_text.strip():
                        result.setdefault("meta", {})["stderr"] = stderr_text.strip()[:2000]
                    return result
            except json.JSONDecodeError:
                pass
        return {"text": stdout_text.strip(), "meta": {"stderr": stderr_text.strip()[:2000]} or {}}


def make_script_runner(manifest):
    """为 script/python_script Skill 生成专属执行闭包(impl 契约签名)

    支持社区包多文件脚本树: script.files 中的伴随文件(协作模块/模板/Schema)
    随入口脚本落沙箱根目录(import office / templates 等相对引用可解析)
    """
    script_spec = manifest.script or {}
    language = str(script_spec.get("language") or "python")
    code = str(script_spec.get("code") or "")
    env_allowed = list(script_spec.get("env_allowed") or [])
    extra_files = {
        str(rel): str(content)
        for rel, content in (script_spec.get("files") or {}).items()
    }

    async def run(skill_input: dict, ctx, caps, progress) -> dict:
        await progress(30, f"沙箱执行 {language} 脚本")
        result = await execute_in_sandbox(
            language, code, skill_input,
            env_allowed=env_allowed,
            timeout_s=manifest.execution.inline_timeout_s,
            extra_files=extra_files,
        )
        await progress(100, "执行完成")
        result.setdefault("meta", {})["sandbox"] = {
            "language": language, "isolated": True,
            "extra_files": len(extra_files),
        }
        return result

    return run
