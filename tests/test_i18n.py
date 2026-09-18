"""i18n 同步契约测试：工具在临时树上自测 + 仓库实时戳/横幅校验（离线）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_i18n() -> ModuleType:
    spec = importlib.util.spec_from_file_location("i18n_tool", ROOT / "scripts" / "i18n.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


i18n = _load_i18n()


def _pair(
    root: Path, stem: str, *, en_body: str = "# Doc", zh_body: str = "# 文档"
) -> tuple[Path, Path]:
    en = root / f"{stem}.md"
    zh = root / f"{stem}.zh.md"
    en.write_text(en_body, encoding="utf-8")
    zh.write_text(zh_body, encoding="utf-8")
    i18n.finalize(en)
    return en, zh


def test_finalize_writes_stamp_and_banners(tmp_path: Path) -> None:
    en, zh = _pair(tmp_path, "a")
    text_en = en.read_text(encoding="utf-8")
    text_zh = zh.read_text(encoding="utf-8")
    assert text_en.startswith("<!-- i18n: source=a.zh.md sha256=")
    assert "> **English** | [中文](a.zh.md)" in text_en
    assert "> **中文** | [English](a.md)" in text_zh
    assert i18n.check_stamps(tmp_path) == []


def test_check_stamps_detects_stale_and_missing(tmp_path: Path) -> None:
    _en, zh = _pair(tmp_path, "a")
    zh.write_text("# 文档已改（英文未同步）", encoding="utf-8")
    errors = i18n.check_stamps(tmp_path)
    assert any("过期" in e for e in errors)

    _pair(tmp_path, "b")
    (tmp_path / "b.md").write_text("# no header\n", encoding="utf-8")
    errors = i18n.check_stamps(tmp_path)
    assert any("缺少 i18n 戳" in e for e in errors)
    assert any("缺少语言横幅" in e for e in errors)


def test_check_links_broken_and_language_mismatch(tmp_path: Path) -> None:
    _pair(tmp_path, "a")
    _pair(tmp_path, "b")
    (tmp_path / "a.zh.md").write_text("[B](b.md)", encoding="utf-8")  # zh → 英文名：错配
    (tmp_path / "a.md").write_text("[B](b.zh.md)", encoding="utf-8")  # en → 中文名：错配
    (tmp_path / "b.zh.md").write_text("[C](c.md)", encoding="utf-8")  # 断裂
    errors = i18n.check_links(tmp_path)
    assert any("链接断裂" in e for e in errors)
    assert sum(1 for e in errors if "应链" in e) == 2


def test_check_links_accepts_same_language(tmp_path: Path) -> None:
    _pair(tmp_path, "a")
    _pair(tmp_path, "b")
    (tmp_path / "a.zh.md").write_text("[B](b.zh.md)", encoding="utf-8")
    (tmp_path / "a.md").write_text("[B](b.md)", encoding="utf-8")
    assert i18n.check_links(tmp_path) == []


def test_exempt_single_language_file_skips_language_rule(tmp_path: Path) -> None:
    _pair(tmp_path, "a")
    _pair(tmp_path, "b")
    (tmp_path / "note.md").write_text("[B](b.md)", encoding="utf-8")  # 单语文件豁免
    assert i18n.check_links(tmp_path) == []


def test_audit_unpaired(tmp_path: Path) -> None:
    _pair(tmp_path, "a")
    (tmp_path / "solo.md").write_text("# solo", encoding="utf-8")
    assert i18n.audit_unpaired(tmp_path) == ["solo.md"]


def test_relink_rewrites_language_siblings(tmp_path: Path) -> None:
    _pair(tmp_path, "a")
    _pair(tmp_path, "b")
    (tmp_path / "a.zh.md").write_text("[B](b.md)", encoding="utf-8")
    (tmp_path / "a.md").write_text("[B](b.zh.md)", encoding="utf-8")
    assert i18n.relink(tmp_path / "a.zh.md") == 1
    assert "[B](b.zh.md)" in (tmp_path / "a.zh.md").read_text(encoding="utf-8")
    assert i18n.relink(tmp_path / "a.md") == 1
    assert "[B](b.md)" in (tmp_path / "a.md").read_text(encoding="utf-8")
    assert i18n.relink(tmp_path / "a.md") == 0  # 幂等


# ── 仓库实时校验（随文档翻译进度保持通过）──────────────────────────────────


def test_repo_stamps_and_banners() -> None:
    assert i18n.check_stamps(ROOT) == []
