# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""复制生成后的脚本，使用真实 CLI/Git；合成报告仅测试状态消费，不是实书放行证据。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from auto_common.workspace import RunStore
from auto_epublizer import orchestrator as orch
from auto_epublizer.qa.artifacts import artifacts_digest
from auto_epublizer.workroot import create_work_root


@pytest.fixture
def root(tmp_path: Path) -> Path:
    result = tmp_path / "copied root"
    create_work_root(result)
    return result


@pytest.fixture
def cli() -> str:
    executable = Path(sys.executable).with_name("auto-epublizer")
    found = str(executable) if executable.is_file() else shutil.which("auto-epublizer")
    assert found, "消费者测试需要真实已安装 auto-epublizer CLI"
    return found


def run(root: Path, script: str, *args: object) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, str(root / "docs" / f"{script}.py"), *map(str, args)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


def released_fixture(root: Path, name: str) -> tuple[RunStore, Path]:
    """真实构建 + 摘要格式夹具；不声称运行过外部 epubcheck。"""
    source = root / f"{name}.md"
    source.write_text("# Chapter\n\nOriginal source paragraph.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=str(root / "workspaces"))
    epub = orch.convert(store)
    # QA 消费边界的合成夹具。报告绑定精确的非默认产物路径。
    chosen = epub.with_name(f"{name}-selected.epub")
    epub.rename(chosen)
    store.save_qa(
        {
            "released": True,
            "released_reason": "ok",
            "epubcheck": {"ran": True, "returncode": 0, "errors": 0},
            "artifacts_epub": str(chosen.relative_to(store.dir)),
            "artifacts_digest": artifacts_digest(store, epub_path=chosen),
        }
    )
    return store, chosen


def ledger_rows(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("|")]
    # 含转义竖线的夹具另行按原文核对。
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines[2:]]
    return header, {row[header.index("slug")]: row for row in rows}


def test_pack_exact_report_artifact_and_source_conversion(root: Path, cli: str) -> None:
    store, epub = released_fixture(root, "alpha")
    assert not list(store.translation_dir.rglob("*.md"))
    # 不能猜 output 里的另一份 EPUB。
    (epub.parent / "decoy.epub").write_bytes(b"not selected")
    result = run(root, "pack_outbox", store.dir, "--batch", "delivery", "--cli", cli)
    assert result.returncode == 0, result.stderr
    batch = root / "outbox" / "delivery"
    assert [p.name for p in (batch / "epub").iterdir()] == [epub.name]
    copied = batch / "epub" / epub.name
    assert copied.read_bytes() == epub.read_bytes()
    assert hashlib.sha256(copied.read_bytes()).hexdigest() in (batch / "MANIFEST.md").read_text()
    repeat = run(root, "pack_outbox", store.dir, "--batch", "delivery", "--cli", cli)
    assert repeat.returncode != 0
    assert "未复制" in repeat.stderr


@pytest.mark.parametrize("change", ["artifact", "report", "unreleased"])
def test_pack_batch_preflight_is_all_or_nothing(root: Path, cli: str, change: str) -> None:
    first, _ = released_fixture(root, "alpha")
    second, epub = released_fixture(root, "beta")
    if change == "artifact":
        epub.write_bytes(epub.read_bytes() + b"changed")
    else:
        report = json.loads(second.report_path.read_text())
        if change == "report":
            report.pop("artifacts_digest")
        else:
            report["released"] = False
        second.save_qa(report)
    result = run(root, "pack_outbox", first.dir, second.dir, "--batch", "refused", "--cli", cli)
    assert result.returncode != 0
    assert not (root / "outbox").exists()


def test_pack_refuses_interrupted_batch_and_name_collision(root: Path, cli: str) -> None:
    first, _ = released_fixture(root, "alpha")
    existing = root / "outbox" / "interrupted"
    existing.mkdir(parents=True)
    sentinel = existing / "existing.epub"
    sentinel.write_bytes(b"keep")
    result = run(root, "pack_outbox", first.dir, "--batch", "interrupted", "--cli", cli)
    assert result.returncode != 0
    assert sentinel.read_bytes() == b"keep"
    second, epub = released_fixture(root, "beta")
    renamed = epub.with_name("alpha-selected.epub")
    epub.rename(renamed)
    report = json.loads(second.report_path.read_text())
    report["artifacts_epub"] = str(renamed.relative_to(second.dir))
    report["artifacts_digest"] = artifacts_digest(second, epub_path=renamed)
    second.save_qa(report)
    collision = run(
        root, "pack_outbox", first.dir, second.dir, "--batch", "collision", "--cli", cli
    )
    assert collision.returncode != 0
    assert not (root / "outbox" / "collision").exists()


def test_ledger_preserves_manual_by_slug_and_machine_cells(root: Path, cli: str) -> None:
    store, _ = released_fixture(root, "alpha")
    output = root / "docs" / "ledger.md"
    args = ("--cli", cli, "--output", output)
    first = run(root, "build_ledger", *args)
    assert first.returncode == 0, first.stderr
    header, rows = ledger_rows(output)
    assert rows["alpha"][header.index("进度")] == "released"
    lines = output.read_text().splitlines()
    for index, line in enumerate(lines):
        if line.startswith("| alpha |"):
            row = line.split("|")
            for name, value in {
                "领域": "历史",
                "摘要": r"人工\|说明",
                "批次": "A",
                "最后修改": "2026-10-17",
            }.items():
                row[header.index(name) + 1] = f" {value} "
            lines[index] = "|".join(row)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    facts = store.preprocessing_dir / "facts.json"
    facts.parent.mkdir(exist_ok=True)
    facts.write_text(json.dumps({"structure": {"totals": {"words": 321}}}))
    orch.set_meta(store, title=r"Renamed \ title | appendix" + "\nSecond\rLine")
    rerun = run(root, "build_ledger", *args)
    assert rerun.returncode == 0, rerun.stderr
    text = output.read_text()
    assert r" 历史 | 人工\|说明 | A | 2026-10-17 |" in text
    assert r"Renamed \\ title \| appendix Second Line" in text
    authority = root / "authority.md"
    subprocess.run(
        [cli, "ledger", "--workspace", str(root / "workspaces"), "-o", str(authority)],
        check=True,
        capture_output=True,
    )
    raw = next(line for line in authority.read_text().splitlines() if line.startswith("| alpha |"))
    merged = next(line for line in text.splitlines() if line.startswith("| alpha |"))
    assert merged.startswith(raw.rsplit("|", 3)[0] + "|")
    assert run(root, "build_ledger", *args).returncode == 0
    assert output.read_text() == text


@pytest.mark.parametrize("fault", ["columns", "duplicate", "cli"])
def test_ledger_failure_keeps_old_file(root: Path, cli: str, fault: str) -> None:
    released_fixture(root, "alpha")
    output = root / "docs" / "ledger.md"
    assert run(root, "build_ledger", "--cli", cli, "--output", output).returncode == 0
    text = output.read_text()
    if fault == "columns":
        text = text.replace("| alpha |", "| alpha | surplus |")
    elif fault == "duplicate":
        row = next(line for line in text.splitlines() if line.startswith("| alpha |"))
        text = text.replace(row, row + "\n" + row)
    output.write_text(text)
    result = run(
        root,
        "build_ledger",
        "--cli",
        root / "absent-cli" if fault == "cli" else cli,
        "--output",
        output,
    )
    assert result.returncode != 0
    assert output.read_text() == text


def test_links_real_inline_reference_code_paths_and_exclusions(root: Path) -> None:
    (root / "AGENTS.md").write_text("[docs](docs/)\n", encoding="utf-8")
    (root / "docs" / "ok.md").write_text("ok")
    guide = root / "docs" / "guide.md"
    guide.write_text(
        """[inline](ok.md#section) [ref][local] [local][] [local]
[local]: <ok.md> "title"
`pack_outbox.py` `../workspaces/`
[external](https://invalid.example/file.md) [fragment](#absent)
`../workspaces/<slug>/publication.json` [epub](EPUB/missing.xhtml)
```sh
[example](absent.md)
```
""",
        encoding="utf-8",
    )
    assert run(root, "check_doc_links").returncode == 0
    guide.write_text(
        guide.read_text()
        + "[broken](missing.md)\n[ref][lost]\n[lost]: missing.py\n`missing-dir/`\n"
    )
    result = run(root, "check_doc_links")
    assert result.returncode != 0
    assert "docs/guide.md:10:" in result.stdout
    assert "missing.md" in result.stdout and "missing.py" in result.stdout
    assert "missing-dir/" in result.stdout


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def test_tracked_reconciles_subpath_ignores_without_staging(root: Path) -> None:
    git(root, "init")
    (root / ".gitignore").write_text("docs/__pycache__/\noutbox/\n.tr/\n")
    git(root, "add", ".")
    # 子路径允许不能放宽成整个 outbox，更不能把 .gitignore 当允许清单。
    for name in ("docs/__pycache__/tool.pyc", "outbox/batch/epub/book.epub", ".tr/draft.txt"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    before = git(root, "diff", "--cached", "--name-only").stdout
    result = run(root, "check_tracked", "--repo", root)
    assert result.returncode != 0
    assert "意外忽略：.tr/draft.txt" in result.stdout
    assert "意外忽略：docs/" not in result.stdout
    assert "意外忽略：outbox/batch/epub/" not in result.stdout
    assert run(root, "check_tracked", "--repo", root, "--allow", ".tr/draft.txt").returncode == 0
    secret = root / "outbox" / "batch" / "secret.txt"
    secret.write_text("not an epub")
    denied = run(root, "check_tracked", "--repo", root, "--allow", ".tr/draft.txt")
    assert denied.returncode != 0 and "意外忽略：outbox/batch/secret.txt" in denied.stdout
    assert git(root, "diff", "--cached", "--name-only").stdout == before


def test_tracked_reports_untracked_missing_and_independent_book(root: Path) -> None:
    book = root / "workspaces" / "independent"
    book.mkdir()
    git(book, "init")
    (book / "kept.txt").write_text("tracked")
    git(book, "add", "kept.txt")
    assert run(root, "check_tracked", "--repo", book).returncode == 0
    (book / "kept.txt").unlink()
    (book / "new.txt").write_text("not yet tracked")
    result = run(root, "check_tracked", "--repo", book)
    assert result.returncode != 0
    assert "未跟踪：new.txt" in result.stdout
    assert "跟踪但缺失：kept.txt" in result.stdout


def test_generated_root_links_follow_real_ledger_lifecycle(root: Path, cli: str) -> None:
    assert run(root, "build_ledger", "--cli", cli).returncode == 0
    valid = run(root, "check_doc_links")
    assert valid.returncode == 0, valid.stdout
    (root / "docs" / "工作台账.md").unlink()
    broken = run(root, "check_doc_links")
    assert broken.returncode == 1
    assert "docs/工作台账.md" in broken.stdout


def test_doc_checker_keeps_footnotes_and_real_fence_boundaries(root: Path) -> None:
    note_target = root / "docs" / "note-target.md"
    html_target = root / "docs" / "manual.html"
    note_target.write_text("A real note reference.", encoding="utf-8")
    html_target.write_text("<h1>A real HTML manual</h1>", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "A note.[^n]\n\n[^n]: See [the document](docs/note-target.md).\n\n"
        "```text\n```python\n[code example](missing.md)\n```\n\n"
        "[HTML manual](docs/manual.html)\n",
        encoding="utf-8",
    )
    clean = run(root, "check_doc_links")
    assert clean.returncode == 0, clean.stdout
    html_target.unlink()
    missing_html = run(root, "check_doc_links")
    assert missing_html.returncode == 1
    assert "docs/manual.html" in missing_html.stdout
    html_target.write_text("<h1>Restored manual</h1>", encoding="utf-8")
    note_target.unlink()
    missing_note_link = run(root, "check_doc_links")
    assert missing_note_link.returncode == 1
    assert "docs/note-target.md" in missing_note_link.stdout


def test_failed_manifest_write_does_not_publish_completion(root: Path, cli: str) -> None:
    pytest.importorskip("resource")
    store, epub = released_fixture(root, "tiny")
    # 此消费夹具只隔离写失败，不冒充真实 EPUBCheck：小产物可先复制，较大的清单写入失败。
    epub.write_bytes(b"EPUB")
    report = json.loads(store.report_path.read_text(encoding="utf-8"))
    report["artifacts_digest"] = artifacts_digest(store, epub_path=epub)
    store.save_qa(report)
    wrapper = (
        "import resource,runpy,sys;"
        "resource.setrlimit(resource.RLIMIT_FSIZE,(256,256));"
        "sys.argv=sys.argv[1:];"
        "runpy.run_path(sys.argv[0],run_name='__main__')"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            wrapper,
            str(root / "docs" / "pack_outbox.py"),
            str(store.dir),
            "--batch",
            "limited",
            "--cli",
            cli,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    batch = root / "outbox" / "limited"
    assert result.returncode == 1
    assert (batch / "epub" / epub.name).read_bytes() == b"EPUB"
    assert not (batch / "MANIFEST.md").exists()
    retry = run(root, "pack_outbox", store.dir, "--batch", "limited", "--cli", cli)
    assert retry.returncode == 1
    assert not (batch / "MANIFEST.md").exists()
