"""配置模型测试：默认值、YAML 加载、快照（无任何 LLM 段——唯一 LLM 原则）。"""

from __future__ import annotations

from auto_common.config import Config, load_config


def test_defaults() -> None:
    cfg = Config()
    assert cfg.language.target == "zh-CN"
    assert cfg.qc.length_ratio == {"too_short": 0.30, "too_long": 3.0}
    assert cfg.pipeline.bilingual is False
    # 唯一 LLM 原则：配置模型没有任何 LLM provider 段
    assert "llm" not in Config.model_fields
    assert "segment" not in Config.model_fields


def test_load_config_from_yaml(tmp_path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "language:\n  target: ja\npipeline:\n  bilingual: true\n",
        encoding="utf-8",
    )
    cfg = load_config(yaml_path)
    assert cfg.language.target == "ja"
    assert cfg.pipeline.bilingual is True


def test_load_config_ignores_removed_llm_section(tmp_path) -> None:
    """旧工作区/旧配置文件残留 llm 段时静默忽略（向后兼容）。"""
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "llm:\n  provider: deepseek\n  base_url: https://x\nlanguage:\n  target: ja\n",
        encoding="utf-8",
    )
    cfg = load_config(yaml_path)
    assert cfg.language.target == "ja"
    assert "llm" not in Config.model_fields


def test_load_config_missing_file_returns_defaults(tmp_path) -> None:
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg.language.target == "zh-CN"


def test_snapshot_roundtrip() -> None:
    cfg = Config()
    snap = cfg.snapshot()
    assert snap["language"]["target"] == "zh-CN"
    assert snap["qc"]["epubcheck"]["jar"].endswith("epubcheck.jar")
    assert "llm" not in snap
