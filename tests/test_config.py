"""配置模型测试：默认值、YAML 加载、快照。"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_common.config import Config, load_config


def test_defaults() -> None:
    cfg = Config()
    assert cfg.language.target == "zh-CN"
    assert cfg.llm.provider == "openai-compatible"
    assert cfg.llm.api_key_env == "DEEPSEEK_API_KEY"
    assert set(cfg.llm.tiers) == {"strong", "cheap", "fast"}
    assert cfg.qc.error_rate_threshold == 0.0001
    assert cfg.qc.length_ratio == {"too_short": 0.30, "too_long": 3.0}
    assert cfg.segment.max_chars_per_segment == 1200


def test_load_config_from_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "language:\n  target: ja\nllm:\n  provider: deepseek\n  base_url: https://x\n",
        encoding="utf-8",
    )
    cfg = load_config(yaml_path)
    assert cfg.language.target == "ja"
    assert cfg.llm.provider == "deepseek"
    assert cfg.llm.base_url == "https://x"
    assert cfg.qc.error_rate_threshold == 0.0001


def test_load_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg.language.target == "zh-CN"


def test_snapshot_roundtrip() -> None:
    cfg = Config()
    snap = cfg.snapshot()
    assert snap["language"]["target"] == "zh-CN"
    assert snap["qc"]["epubcheck"]["jar"].endswith("epubcheck.jar")


def test_api_key_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    assert Config().llm.api_key() == "sk-test"
