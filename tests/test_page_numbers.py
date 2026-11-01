# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""目录/索引页码策略：只声明，不改源件；重复目录只报候选。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch
from auto_epublizer.preprocess.artifacts import ArtifactContractError, read_page_number_policies


def _ws(tmp_path: Path):
    source = tmp_path / "book.md"
    source.write_text(
        "# 目录\n\nAlpha 1\n\nBeta 2\n\n# 目录\n\nAlpha 1\n\nBeta 2\n\n# 索引\n\nAlpha 1\n",
        encoding="utf-8",
    )
    return orch.init(str(source), workspace_dir=str(tmp_path / "ws"))


def test_page_number_policy_declares_without_touching_source(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    policy = store.preprocessing_dir / "page_numbers.csv"
    policy.write_text(
        "unit,policy,reason,evidence\n"
        "front-toc,product,回填最终 PDF 页序,output/book.pdf p17-18\n"
        "back-index,original,索引保留原版页码,\n",
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in store.structured_dir.rglob("*.md")}
    data = orch.page_number_evidence(store)
    by_unit = {item["unit"]: item for item in data["units"]}
    assert set(by_unit) == {"front-toc", "front-toc-2", "back-index"}
    assert by_unit["front-toc"]["declared_policy"] == "product"
    assert by_unit["front-toc-2"]["declared_policy"] is None  # 未声明不等于 original
    assert by_unit["back-index"]["declared_policy"] == "original"
    assert by_unit["front-toc"]["number_candidate_count"] == 2
    assert by_unit["front-toc"]["applied"] is False
    assert any(
        set(group["units"]) == {"front-toc", "front-toc-2"}
        for group in data["duplicate_toc_candidates"]
    )
    assert {path: path.read_bytes() for path in store.structured_dir.rglob("*.md")} == before


def test_product_policy_without_evidence_is_rejected(tmp_path: Path) -> None:
    store = _ws(tmp_path)
    (store.preprocessing_dir / "page_numbers.csv").write_text(
        "unit,policy,reason,evidence\nfront-toc,product,回填最终页序,\n",
        encoding="utf-8",
    )
    with pytest.raises(ArtifactContractError, match="映射证据"):
        read_page_number_policies(store)


@pytest.mark.parametrize("policy", ["original", "none"])
def test_non_product_policies_are_declarations_only(tmp_path: Path, policy: str) -> None:
    store = _ws(tmp_path)
    (store.preprocessing_dir / "page_numbers.csv").write_text(
        f"unit,policy,reason,evidence\nback-index,{policy},按体例处理,\n",
        encoding="utf-8",
    )
    data = orch.page_number_evidence(store)
    item = next(row for row in data["units"] if row["unit"] == "back-index")
    assert item["declared_policy"] == policy
    assert item["applied"] is False
    assert json.loads(json.dumps(data, ensure_ascii=False))["schema_version"] == "1"
