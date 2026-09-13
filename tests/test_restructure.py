"""结构重建登记测试（S3）：structure.csv 校验 + 状态语义 + CLI 冒烟。"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

runner = CliRunner()


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# One\n\nAlpha text.\n\n# Two\n\nBeta text.\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _write_csv(store, rows: list[dict]) -> None:
    p = store.preprocessing_dir / "structure.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "region", "kind", "title", "level", "rel_path"])
        w.writeheader()
        w.writerows(rows)


def _rows(store) -> list[dict]:
    return [
        {
            "id": u.id,
            "region": (u.meta or {}).get("region", "body"),
            "kind": u.kind,
            "title": u.title,
            "level": (u.meta or {}).get("level", 1),
            "rel_path": (u.meta or {}).get("rel_path", ""),
        }
        for u in store.load_publication().units
    ]


def test_restructure_unchanged_preserves_status(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    store.set_unit_status("ch01", "aligned")
    _write_csv(store, _rows(store))
    result = orch.restructure(store)
    assert result == {"units": 2, "reset": [], "added": [], "removed": []}
    assert store.load_publication().unit("ch01").status == "aligned"
    assert store.load_publication().unit("ch02").status == "split"


def test_restructure_changed_resets_and_added(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    # ch02 标题变更（文件 + 清单同步改）
    (store.structured_dir / "body" / "ch02.md").write_text("# 二\n\nBeta text.\n", encoding="utf-8")
    rows = _rows(store)
    rows[1]["title"] = "二"
    # 新增 ch03
    (store.structured_dir / "body" / "ch03.md").write_text("# 三\n\nGamma.\n", encoding="utf-8")
    rows.append(
        {
            "id": "ch03",
            "region": "body",
            "kind": "chapter",
            "title": "三",
            "level": 1,
            "rel_path": "body/ch03.md",
        }
    )
    _write_csv(store, rows)
    result = orch.restructure(store)
    assert result["reset"] == ["ch02"] and result["added"] == ["ch03"] and result["removed"] == []
    pub = store.load_publication()
    assert pub.unit("ch02").status == "split" and pub.unit("ch02").title == "二"
    assert pub.unit("ch03").status == "split"


def test_restructure_removed_unit(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    (store.structured_dir / "body" / "ch02.md").unlink()
    rows = [r for r in _rows(store) if r["id"] != "ch02"]
    _write_csv(store, rows)
    result = orch.restructure(store)
    assert result["removed"] == ["ch02"]
    assert store.load_publication().unit("ch02") is None


def test_restructure_requires_csv(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "缺少结构清单" in str(e.value)


def test_restructure_contract_errors(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    good = _rows(store)

    _write_csv(store, [dict(good[0], id="1bad")])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "id 非法" in str(e.value)

    _write_csv(store, [good[0], dict(good[0])])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "id 重复" in str(e.value)

    _write_csv(store, [dict(good[0], region="body", rel_path="frontmatter/x.md")])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "与 region 不符" in str(e.value)

    _write_csv(store, [dict(good[0], title="不对")])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "title 与文件首行不一致" in str(e.value)

    _write_csv(store, [dict(good[0], level=7)])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "level 越界" in str(e.value)

    # 孤儿 md：结构清单未列全（ch02 被漏登）
    _write_csv(store, [good[0]])
    with pytest.raises(orch.OrchestrationError) as e:
        orch.restructure(store)
    assert "未登记的 md" in str(e.value)


def test_restructure_cli_smoke(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    _write_csv(store, _rows(store))
    res = runner.invoke(app, ["restructure", "--workspace", str(store.dir)])
    assert res.exit_code == 0, res.output
    assert "结构已登记" in res.output
