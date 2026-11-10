"""#30：长期多书工作根脚手架（work-root 命令）。"""

from __future__ import annotations

from pathlib import Path

from auto_epublizer.workroot import create_work_root, template_dir

_TOP_FILES = ("AGENTS.md", "README.md", "config.example.yaml")
_DIRS = ("inbox", "sources", "workspaces", "docs", "references")


def test_create_work_root_generates_skeleton(tmp_path: Path) -> None:
    target = tmp_path / "work"
    result = create_work_root(target)
    for name in _TOP_FILES:
        assert (target / name).is_file(), f"缺 {name}"
    for d in _DIRS:
        assert (target / d).is_dir(), f"缺目录 {d}"
    # 内容以仓库模板为准（单一权威）
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == (
        template_dir() / "AGENTS.md"
    ).read_text(encoding="utf-8")
    assert result["created"]


def test_create_work_root_idempotent_and_force(tmp_path: Path) -> None:
    target = tmp_path / "work"
    create_work_root(target)
    again = create_work_root(target)
    assert again["created"] == []
    assert again["skipped"]  # 已存在 → 跳过

    (target / "README.md").write_text("changed", encoding="utf-8")
    create_work_root(target)  # 默认不覆盖
    assert (target / "README.md").read_text(encoding="utf-8") == "changed"

    create_work_root(target, force=True)
    assert (target / "README.md").read_text(encoding="utf-8") == (
        template_dir() / "README.md"
    ).read_text(encoding="utf-8")


def test_create_work_root_dry_run_previews_every_file_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "preview"
    preview = create_work_root(target, dry_run=True)
    assert preview["dry_run"] is True
    assert preview["created"]
    assert not target.exists()  # 不创建目标目录，也不写任何文件

    real = create_work_root(target)
    assert real["created"] == preview["created"]
    assert real["skipped"] == preview["skipped"]

    changed = tmp_path / "mixed"
    create_work_root(changed)
    before = {path: path.read_bytes() for path in changed.rglob("*") if path.is_file()}
    again = create_work_root(changed, dry_run=True, force=True)
    assert again["created"] == sorted(again["created"])
    assert {path: path.read_bytes() for path in changed.rglob("*") if path.is_file()} == before


def test_mature_work_root_reports_missing_without_writing(tmp_path: Path) -> None:
    """D3：成熟工作根不自动补顶层文件，只报告缺项；--force 才补齐。"""
    target = tmp_path / "work"
    create_work_root(target)
    (target / "README.md").unlink()
    before = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}

    result = create_work_root(target)
    assert result["mature"] is True
    assert "README.md" in result["missing"]
    assert result["created"] == []
    assert not (target / "README.md").exists()
    assert {p: p.read_bytes() for p in target.rglob("*") if p.is_file()} == before

    preview = create_work_root(target, dry_run=True)
    assert preview["created"] == [] and "README.md" in preview["missing"]

    forced = create_work_root(target, force=True)
    assert "README.md" in forced["created"]
    assert (target / "README.md").is_file()
