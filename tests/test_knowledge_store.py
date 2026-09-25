"""统一术语库/知识库测试：目录解析、git 维护、合并/导出/冲突、CLI。"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_common.config import Config
from auto_epublizer import knowledge
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app
from auto_translator.glossary import (
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_SEED,
    GlossaryEntry,
    StoreEntry,
    export_for_workspace,
    load_store_csv,
    merge_workspace_glossary,
    read_store_conflicts,
    save_store_csv,
    store_stats,
    unresolved_keys,
)

runner = CliRunner()


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# Chapter I\n\nFirst sentence here.\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=tmp_path / "ws")


def _write_glossary(store, text: str) -> None:
    store.analysis_dir.mkdir(parents=True, exist_ok=True)
    (store.analysis_dir / "glossary.csv").write_text(text, encoding="utf-8")


_HEADER = "source,target,type,aliases,gender,reading,status,note\n"


# ── 目录/远端解析 ────────────────────────────────────────────────────────────


def test_resolve_store_dir_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AUTO_EPUBLIZER_HOME", raising=False)
    # 默认 ~/Documents/auto-epublizer
    assert knowledge.resolve_store_dir(None) == tmp_path / "home" / "Documents" / "auto-epublizer"
    # 配置覆盖
    cfg = Config.model_validate({"paths": {"knowledge_dir": str(tmp_path / "cfg")}})
    assert knowledge.resolve_store_dir(cfg) == tmp_path / "cfg"
    # 环境变量覆盖配置
    monkeypatch.setenv("AUTO_EPUBLIZER_HOME", str(tmp_path / "env"))
    assert knowledge.resolve_store_dir(cfg) == tmp_path / "env"
    # --dir 覆盖环境变量
    assert knowledge.resolve_store_dir(cfg, override=str(tmp_path / "cli")) == tmp_path / "cli"


def test_resolve_remote_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_EPUBLIZER_REMOTE", raising=False)
    assert knowledge.resolve_remote(None) == ""
    cfg = Config.model_validate({"paths": {"knowledge_remote": "git@cfg:r.git"}})
    assert knowledge.resolve_remote(cfg) == "git@cfg:r.git"
    monkeypatch.setenv("AUTO_EPUBLIZER_REMOTE", "git@env:r.git")
    assert knowledge.resolve_remote(cfg) == "git@env:r.git"
    assert knowledge.resolve_remote(cfg, override="git@cli:r.git") == "git@cli:r.git"


# ── git 维护 ─────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not knowledge.git_available(), reason="git 不可用")
def test_knowledge_init_creates_skeleton_and_git(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    result = knowledge.knowledge_init(store_dir)
    assert result["initialized"] is True
    assert result["committed"] is True
    for name in ("README.md", ".gitignore", "terminology.csv", "conflicts.jsonl"):
        assert (store_dir / name).is_file()
    assert (store_dir / "knowledge" / "INDEX.md").is_file()
    assert knowledge.is_git_repo(store_dir)
    assert knowledge.git_state(store_dir)["dirty"] is False
    # 幂等：重复 init 不报错，且骨架不被覆盖
    (store_dir / "README.md").write_text("custom", encoding="utf-8")
    knowledge.knowledge_init(store_dir)
    assert (store_dir / "README.md").read_text(encoding="utf-8") == "custom"


@pytest.mark.skipif(not knowledge.git_available(), reason="git 不可用")
def test_knowledge_import_commits_and_is_idempotent(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_glossary(
        store,
        _HEADER
        + "Jay Gatsby,杰伊·盖茨比,person,James Gatz,male,,confirmed,主人公\n"
        + "West Egg,西卵,place,,,,confirmed,\n",
    )
    store_dir = tmp_path / "store"
    knowledge.knowledge_init(store_dir)

    first = knowledge.knowledge_import(store_dir, store, src_lang="en")
    assert first["added"] == 2
    assert first["committed"] is True
    assert knowledge.git_state(store_dir)["dirty"] is False
    entries = load_store_csv(store_dir / "terminology.csv")
    assert {e.source for e in entries} == {"Jay Gatsby", "West Egg"}
    assert all(e.src_lang == "en" and e.tgt_lang == "zh-CN" and e.book == "book" for e in entries)

    # 幂等：重复导入不新增、不重复记账
    second = knowledge.knowledge_import(store_dir, store, src_lang="en")
    assert second["added"] == 0
    assert len(load_store_csv(store_dir / "terminology.csv")) == 2


# ── 合并/导出领域逻辑 ────────────────────────────────────────────────────────


def test_merge_adds_updates_and_records_conflict() -> None:
    existing = [
        StoreEntry(
            source="zone",
            target="赤区",
            type="term",
            status=STATUS_CONFIRMED,
            src_lang="en",
            tgt_lang="zh-CN",
            book="book-a",
        )
    ]
    ws = [
        GlossaryEntry(source="zone", target="赤区", type="term", status=STATUS_CONFIRMED),
        GlossaryEntry(source="zone", target="苏区", type="term", status=STATUS_CONFIRMED),
        GlossaryEntry(source="new term", target="新术语", type="term", status=STATUS_SEED),
    ]
    result = merge_workspace_glossary(existing, ws, src_lang="en", tgt_lang="zh-CN", book="book-b")
    # zone/赤区 命中既有 → 不新增；zone/苏区 → 冲突；new term → 新增
    assert result.added == 2
    assert len(result.conflicts) == 1
    c = result.conflicts[0]
    assert c.source == "zone" and c.existing_target == "赤区" and c.proposed_target == "苏区"
    assert set(c.books) == {"book-a", "book-b"}
    assert unresolved_keys(result.entries) == [("en", "zh-CN", "zone")]


def test_merge_idempotent_on_rerun() -> None:
    ws = [GlossaryEntry(source="zone", target="苏区", status=STATUS_CONFIRMED)]
    first = merge_workspace_glossary([], ws, src_lang="en", tgt_lang="zh-CN", book="b")
    second = merge_workspace_glossary(first.entries, ws, src_lang="en", tgt_lang="zh-CN", book="b")
    assert second.added == 0
    assert len(second.entries) == 1
    assert second.conflicts == []


def test_export_filters_lang_pair_and_prefers_confirmed() -> None:
    entries = [
        StoreEntry(
            source="a", target="甲", status=STATUS_CONFIRMED, src_lang="en", tgt_lang="zh-CN"
        ),
        StoreEntry(source="b", target="乙", status=STATUS_SEED, src_lang="en", tgt_lang="zh-CN"),
        StoreEntry(
            source="c", target="丙", status=STATUS_CONFIRMED, src_lang="ru", tgt_lang="zh-CN"
        ),
        StoreEntry(
            source="d", target="丁", status=STATUS_CONFLICT, src_lang="en", tgt_lang="zh-CN"
        ),
    ]
    default = export_for_workspace(entries, src_lang="en", tgt_lang="zh-CN")
    assert {e.source for e in default} == {"a"}  # 仅同语对 confirmed
    pending = export_for_workspace(entries, src_lang="en", tgt_lang="zh-CN", include_pending=True)
    assert {e.source for e in pending} == {"a", "b"}  # 冲突态不导出


def test_export_prefers_confirmed_when_key_conflicted() -> None:
    entries = [
        StoreEntry(
            source="zone", target="赤区", status=STATUS_CONFIRMED, src_lang="en", tgt_lang="zh-CN"
        ),
        StoreEntry(
            source="zone", target="苏区", status=STATUS_CONFLICT, src_lang="en", tgt_lang="zh-CN"
        ),
    ]
    out = export_for_workspace(entries, src_lang="en", tgt_lang="zh-CN", include_pending=True)
    assert [(e.source, e.target) for e in out] == [("zone", "赤区")]


def test_unresolved_keys_close_after_arbitration() -> None:
    entries = [
        StoreEntry(
            source="zone", target="赤区", status=STATUS_CONFIRMED, src_lang="en", tgt_lang="zh-CN"
        ),
        StoreEntry(
            source="zone", target="苏区", status=STATUS_CONFLICT, src_lang="en", tgt_lang="zh-CN"
        ),
    ]
    assert len(unresolved_keys(entries)) == 1
    # agent 裁决：删除落败条目 → 自动归零
    entries.pop()
    assert unresolved_keys(entries) == []


def test_store_stats_counts() -> None:
    entries = [
        StoreEntry(
            source="a",
            target="甲",
            status=STATUS_CONFIRMED,
            src_lang="en",
            tgt_lang="zh-CN",
            book="b1",
        ),
        StoreEntry(
            source="b", target="乙", status=STATUS_SEED, src_lang="en", tgt_lang="zh-CN", book="b1"
        ),
        StoreEntry(
            source="c",
            target="丙",
            status=STATUS_CONFIRMED,
            src_lang="ru",
            tgt_lang="zh-CN",
            book="b2",
        ),
    ]
    stats = store_stats(entries)
    assert stats["total"] == 3
    assert stats["by_lang"] == {"en->zh-CN": 2, "ru->zh-CN": 1}
    assert stats["by_status"][STATUS_CONFIRMED] == 2
    assert stats["books"] == ["b1", "b2"]
    assert stats["unresolved"] == 0


# ── 导入/导出往返（工作区 + store）──────────────────────────────────────────


def test_import_export_roundtrip_and_refuse_overwrite(tmp_path: Path) -> None:
    ws1 = _workspace(tmp_path / "one")
    _write_glossary(ws1, _HEADER + "Jay Gatsby,杰伊·盖茨比,person,,male,,confirmed,主人公\n")
    store_dir = tmp_path / "store"
    knowledge.knowledge_init(store_dir)
    knowledge.knowledge_import(store_dir, ws1, src_lang="en")

    # 第二本书（同语对）导出播种
    ws2 = _workspace(tmp_path / "two")
    out = knowledge.knowledge_export(store_dir, ws2, src_lang="en")
    assert out["written"] is True and out["count"] == 1
    terms = (ws2.preprocessing_dir / "terms.csv").read_text(encoding="utf-8")
    assert "Jay Gatsby" in terms and "杰伊·盖茨比" in terms

    # 已有内容时拒绝覆盖，需 --force
    again = knowledge.knowledge_export(store_dir, ws2, src_lang="en")
    assert again["written"] is False and "已有内容" in again["reason"]
    forced = knowledge.knowledge_export(store_dir, ws2, src_lang="en", force=True)
    assert forced["written"] is True


def test_import_requires_src_lang_when_unknown(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    _write_glossary(ws, _HEADER + "a,甲,term,,,,confirmed,\n")
    store_dir = tmp_path / "store"
    # publication 的 meta.language 默认为空（auto 未回写）
    pub = ws.load_publication()
    assert not pub.meta.language
    with pytest.raises(ValueError, match="--src-lang"):
        knowledge.knowledge_import(store_dir, ws)


def test_export_lang_pair_isolated(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws")
    store_dir = tmp_path / "store"
    knowledge.knowledge_init(store_dir)
    save_store_csv(
        store_dir / "terminology.csv",
        [
            StoreEntry(
                source="a", target="甲", status=STATUS_CONFIRMED, src_lang="en", tgt_lang="zh-CN"
            ),
            StoreEntry(
                source="b", target="乙", status=STATUS_CONFIRMED, src_lang="ru", tgt_lang="zh-CN"
            ),
        ],
    )
    out = knowledge.knowledge_export(store_dir, ws, src_lang="ru")
    assert out["count"] == 1
    terms = (ws.preprocessing_dir / "terms.csv").read_text(encoding="utf-8")
    assert "b,乙" in terms and "a,甲" not in terms


def test_status_reports_stats_and_conflict_ledger(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws")
    _write_glossary(ws, _HEADER + "zone,赤区,term,,,,confirmed,\n")
    store_dir = tmp_path / "store"
    knowledge.knowledge_init(store_dir)
    knowledge.knowledge_import(store_dir, ws, src_lang="en")
    # 第二本书同键不同译法 → 冲突账本
    _write_glossary(ws, _HEADER + "zone,苏区,term,,,,confirmed,\n")
    knowledge.knowledge_import(store_dir, ws, src_lang="en")

    status = knowledge.knowledge_status(store_dir)
    assert status["exists"] is True
    assert status["stats"]["total"] == 2
    assert status["stats"]["unresolved"] == 1
    assert status["stats"]["conflicts_ledger"] == 1
    assert len(read_store_conflicts(store_dir / "conflicts.jsonl")) == 1
    assert status["knowledge_files"] == ["INDEX.md"]


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_knowledge_path_and_init(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    result = runner.invoke(app, ["knowledge", "path", "--dir", str(store_dir)])
    assert result.exit_code == 0, result.output
    assert str(store_dir) in result.output

    result = runner.invoke(app, ["knowledge", "init", "--dir", str(store_dir)])
    assert result.exit_code == 0, result.output
    assert "统一库已就绪" in result.output

    result = runner.invoke(app, ["knowledge", "status", "--dir", str(store_dir), "--json"])
    assert result.exit_code == 0, result.output
    assert '"exists": true' in result.output


def test_cli_knowledge_import_export(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws")
    _write_glossary(ws, _HEADER + "Jay Gatsby,杰伊·盖茨比,person,,male,,confirmed,\n")
    store_dir = tmp_path / "store"
    runner.invoke(app, ["knowledge", "init", "--dir", str(store_dir)])

    result = runner.invoke(
        app,
        [
            "knowledge",
            "import",
            "--dir",
            str(store_dir),
            "--workspace",
            str(ws.dir),
            "--src-lang",
            "en",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "已合并进统一库" in result.output

    ws2 = _workspace(tmp_path / "ws2")
    result = runner.invoke(
        app,
        [
            "knowledge",
            "export",
            "--dir",
            str(store_dir),
            "--workspace",
            str(ws2.dir),
            "--src-lang",
            "en",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "已导出" in result.output
    assert (ws2.preprocessing_dir / "terms.csv").is_file()


def test_cli_knowledge_import_requires_src_lang(tmp_path: Path) -> None:
    ws = _workspace(tmp_path / "ws")
    _write_glossary(ws, _HEADER + "a,甲,term,,,,confirmed,\n")
    store_dir = tmp_path / "store"
    result = runner.invoke(
        app, ["knowledge", "import", "--dir", str(store_dir), "--workspace", str(ws.dir)]
    )
    assert result.exit_code != 0
    assert "--src-lang" in result.output


# ── 任意术语 CSV 导入（历史项目入口）────────────────────────────────────────


def test_knowledge_import_file_legacy_categories_and_status(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "category,source,target,note\n"
        "机构,НКВД,内务人民委员部,苏联秘密警察\n"
        "组织机构,El Colegio de México,墨西哥学院,出版社\n"
        "概念,caudillo,考迪罗,\n"
        "职衔,Генеральный комиссар,国家安全总委员,\n"
        "政治派系,Partido,党,\n",
        encoding="utf-8",
    )
    result = knowledge.knowledge_import_file(
        store_dir, csv_path, src_lang="ru", tgt_lang="zh-CN", book="hist", status="confirmed"
    )
    assert result["added"] == 5
    entries = load_store_csv(store_dir / "terminology.csv")
    by = {e.source: e for e in entries}
    assert by["НКВД"].type == "org"
    assert by["El Colegio de México"].type == "org"
    assert by["caudillo"].type == "term"
    assert by["Генеральный комиссар"].type == "term"
    assert by["Partido"].type == "org"
    assert all(e.status == STATUS_CONFIRMED for e in entries)
    assert all(e.book == "hist" and e.src_lang == "ru" for e in entries)


def test_knowledge_import_file_standard_format(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    csv_path = tmp_path / "std.csv"
    csv_path.write_text(
        _HEADER + "fedayeen,费达因,term,,,,seed,敢死队\n",
        encoding="utf-8",
    )
    knowledge.knowledge_import_file(store_dir, csv_path, src_lang="en", tgt_lang="zh-CN", book="b1")
    entries = load_store_csv(store_dir / "terminology.csv")
    assert [(e.source, e.status) for e in entries] == [("fedayeen", STATUS_SEED)]


def test_cli_knowledge_import_csv(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    csv_path = tmp_path / "legacy.csv"
    csv_path.write_text(
        "category,source,target,note\n人物,Peter Fleming,彼得·弗莱明,记者\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "knowledge",
            "import-csv",
            str(csv_path),
            "--src-lang",
            "en",
            "--book",
            "fleming-china",
            "--dir",
            str(store_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "已导入统一库" in result.output
    assert "Peter Fleming" in (store_dir / "terminology.csv").read_text(encoding="utf-8")
