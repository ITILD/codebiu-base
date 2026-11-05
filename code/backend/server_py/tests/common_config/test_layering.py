"""配置加载测试(common/config/index)

覆盖: 基线必选 / config.local_file 指定覆盖文件 / 文件缺失直接报错 /
深合并保留同级键 / CODEBIU_* 环境变量最高优先级(自动类型转换)
"""
from pathlib import Path

import pytest
import yaml

from common.config.index import _load, _settings_files


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


# ==================== 文件清单解析 ====================

def test_settings_files_requires_base(tmp_path: Path, monkeypatch):
    """基线缺失即失败(必须在 server_py 目录下启动)"""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="基线配置文件不存在"):
        _settings_files()


def test_settings_files_no_local_configured_warns(tmp_path: Path, monkeypatch, caplog):
    """未配置 config.local_file 时只用基线, 并给出提示"""
    monkeypatch.chdir(tmp_path)
    _write_yaml(tmp_path / "config.yaml", {"state": {"is_dev": True}})

    with caplog.at_level("WARNING"):
        files = _settings_files()
    assert files == [Path("config.yaml")]
    assert any("config.local_file" in r.message for r in caplog.records)


def test_settings_files_uses_configured_file(tmp_path: Path, monkeypatch):
    """config.local_file 指向的文件存在则追加为覆盖层"""
    monkeypatch.chdir(tmp_path)
    _write_yaml(
        tmp_path / "config.yaml",
        {"config": {"local_file": "config.dev.yaml"}, "state": {"is_dev": True}},
    )
    (tmp_path / "config.dev.yaml").write_text("token:\n  expire_minutes: 60\n", encoding="utf-8")

    assert _settings_files() == [Path("config.yaml"), Path("config.dev.yaml")]


def test_settings_files_arbitrary_name(tmp_path: Path, monkeypatch):
    """部署时可切换为任意 config.**.yaml"""
    monkeypatch.chdir(tmp_path)
    _write_yaml(
        tmp_path / "config.yaml",
        {"config": {"local_file": "config.prod.yaml"}, "state": {"is_dev": True}},
    )
    (tmp_path / "config.prod.yaml").write_text("token:\n  expire_minutes: 60\n", encoding="utf-8")

    assert _settings_files() == [Path("config.yaml"), Path("config.prod.yaml")]


def test_settings_files_missing_configured_file_raises(tmp_path: Path, monkeypatch):
    """指定的覆盖文件缺失: 直接报错, 防部署静默回退基线"""
    monkeypatch.chdir(tmp_path)
    _write_yaml(
        tmp_path / "config.yaml",
        {"config": {"local_file": "config.prod.yaml"}, "state": {"is_dev": True}},
    )

    with pytest.raises(FileNotFoundError, match="config.prod.yaml"):
        _settings_files()


# ==================== 合并 + 环境变量 ====================

def test_local_overrides_base_and_keeps_siblings(tmp_path: Path, monkeypatch):
    """覆盖层只写需要改的键: 深合并, 未覆盖的同级键保留"""
    monkeypatch.chdir(tmp_path)
    _write_yaml(
        tmp_path / "config.yaml",
        {
            "state": {"is_dev": True},
            "token": {"algorithm": "HS256", "expire_minutes": 30, "secret_key": "base"},
            "websearch": {"timeout": 15, "max_results": 10, "tavily": {"api_key": ""}},
        },
    )
    _write_yaml(
        tmp_path / "config.dev.yaml",
        {"token": {"expire_minutes": 60}, "websearch": {"timeout": 99}},
    )

    conf = _load(["config.yaml", "config.dev.yaml"])
    assert conf.state.is_dev is True
    assert conf.get("token").get("algorithm") == "HS256"  # 兄弟键保留
    assert conf.get("token").get("expire_minutes") == 60
    assert conf.get("websearch").get("max_results") == 10  # 部分覆盖不丢兄弟键
    assert conf.get("websearch").get("timeout") == 99
    assert conf.get("websearch").get("tavily").get("api_key") == ""  # 嵌套子组深合并


def test_env_vars_override_files(tmp_path: Path, monkeypatch):
    """CODEBIU_* 环境变量键级覆盖最高优先级(字符串自动转数值)"""
    monkeypatch.chdir(tmp_path)
    _write_yaml(
        tmp_path / "config.yaml",
        {"token": {"secret_key": "base", "expire_minutes": 30}},
    )
    monkeypatch.setenv("CODEBIU_TOKEN__SECRET_KEY", "env-key")
    monkeypatch.setenv("CODEBIU_TOKEN__EXPIRE_MINUTES", "45")

    conf = _load(["config.yaml"])
    assert conf.get("token").get("secret_key") == "env-key"
    assert conf.get("token").get("expire_minutes") == 45
    assert isinstance(conf.get("token").get("expire_minutes"), int)


# ==================== 真实全局单例冒烟 ====================

def test_real_conf_loaded():
    """真实 conf 可用: 基线按 config.local_file 叠加覆盖文件, 关键节存在"""
    from common.config.index import conf, is_dev

    assert isinstance(is_dev, bool)
    assert conf.get("state") is not None
    assert conf.get("server") is not None
    assert conf.get("dir") is not None
    assert conf.get("db_rel") is not None
