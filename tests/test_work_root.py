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
