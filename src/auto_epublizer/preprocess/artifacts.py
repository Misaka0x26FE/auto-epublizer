# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""预处理产物的读取与契约校验（catalog.csv / repairs.jsonl）。

C 组最小重构：原实现位于 ``orchestrator.py``，但它们是**预处理层产物的 schema 契约**
（skills/auto-epublizer/references/preprocessing.md、docs/semantic-repair.md §3.3），
归 ``preprocess`` 拥有；编排层只导入使用（``orch.read_catalog`` 仍可用，名字经由导入
重导出）。为不引入 preprocess→orchestrator 的反向依赖，契约错误用本模块的
``ArtifactContractError``（``ValueError`` 子类，CLI 统一按可预期用户错误处理）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from auto_common.workspace import RunStore


class ArtifactContractError(ValueError):
    """预处理产物违反已登记契约（可预期用户错误；中文提示带行号/列名）。"""


def read_repairs(store: RunStore) -> list[dict[str, Any]] | None:
    """读取语义整备留痕（preprocessing/repairs.jsonl；S2 契约）。

    文件不存在 → None（全部检查跳过，零破坏）。每行一个修复动作：
    ``unit`` 必填且必须存在于 publication.units；``kind``（见下）/``status``
    （done|unresolved）枚举；``summary`` 必填非空；``evidence`` 为工作区相对
    路径且必须存在（防杜撰）；``pages``/``count`` 非法类型报错。
    违反 → ArtifactContractError（中文提示，带行号）。
    """
    import json

    path = store.preprocessing_dir / "repairs.jsonl"
    if not path.is_file():
        return None
    kinds = {
        "line_join",
        "hyphen",
        "ocr_char",
        "mojibake",
        "punct",
        "header_footer",
        "footnote",
        "order",
        "heading",
        "boundary",
        "classification",
        "garbage",
        "media",
        "metadata",
        "other",
    }
    statuses = {"done", "unresolved"}
    unit_ids = {u.id for u in store.load_publication().units}
    rows: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行不是合法 JSON：{e}") from None
        if not isinstance(row, dict):
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行必须是 JSON 对象")
        unit = str(row.get("unit") or "")
        kind = str(row.get("kind") or "")
        status = str(row.get("status") or "")
        summary = str(row.get("summary") or "").strip()
        if not unit:
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行 unit 必填")
        # 结构重建可能删除单元（issue #23）：引用了已消失单元的历史行**不阻断 qa**，
        # 标记 unit_missing 交由 qa 出 warning（done 是已完成的历史动作，unresolved 也
        # 只降级提示，避免整条流水线中断）。
        unit_missing = unit not in unit_ids
        if kind not in kinds:
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行 kind 非法：{kind!r}")
        if status not in statuses:
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行 status 非法：{status!r}")
        if not summary:
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行 summary 必填")
        evidence = row.get("evidence")
        if evidence:
            ev = Path(str(evidence))
            if ev.is_absolute() or ".." in ev.parts or not (store.dir / ev).is_file():
                raise ArtifactContractError(
                    f"repairs.jsonl 第 {lineno} 行 evidence 不存在或非法：{evidence!r}"
                )
        pages = row.get("pages")
        if pages is not None and (
            not isinstance(pages, list) or not all(isinstance(p, int) for p in pages)
        ):
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行 pages 必须是整数数组")
        count = row.get("count")
        if count is not None and not isinstance(count, int):
            raise ArtifactContractError(f"repairs.jsonl 第 {lineno} 行 count 必须是整数")
        row = {**row, "unit_missing": True} if unit_missing else row
        rows.append(row)
    return rows


def read_catalog(store: RunStore) -> list[dict[str, Any]] | None:
    """读取源内容盘点（preprocessing/catalog.csv；S4.4 SourceCatalog 最小形态）。

    文件不存在 → None（全部检查跳过，零破坏）。列契约：
    ``item,kind,status,locator,unit_id,note``——kind ∈ toc|figure|table|footnote|
    section|physical；status ∈ included|physical|excluded|unresolved|absent；
    included 行 unit_id 必填；excluded/absent 行 note 必填理由。
    ``absent`` = 源件本身不含该内容（如题注所指插图不在源包里）——既非「有意排除」，
    也非「未决」，因此不阻断放行（现场报告 #8：缺图只能记 unresolved 或谎称 excluded）。
    取值非法/列缺失 → ArtifactContractError（带行号）。
    """
    import csv

    path = store.preprocessing_dir / "catalog.csv"
    if not path.is_file():
        return None
    kinds = {"toc", "figure", "table", "footnote", "section", "physical"}
    statuses = {"included", "physical", "excluded", "unresolved", "absent"}
    required = ["item", "kind", "status", "locator", "unit_id", "note"]
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ArtifactContractError(
                f"catalog.csv 列契约不符（要求 {','.join(required)}）：{path}"
            )
        for i, row in enumerate(reader, start=2):
            if not (row.get("item") or "").strip():
                raise ArtifactContractError(f"catalog.csv 第 {i} 行：item 为空")
            if (row.get("kind") or "") not in kinds:
                raise ArtifactContractError(
                    f"catalog.csv 第 {i} 行：kind 非法（{row.get('kind')}）"
                )
            status_val = row.get("status") or ""
            if status_val not in statuses:
                raise ArtifactContractError(f"catalog.csv 第 {i} 行：status 非法（{status_val}）")
            if status_val == "included" and not (row.get("unit_id") or "").strip():
                raise ArtifactContractError(f"catalog.csv 第 {i} 行：included 项缺 unit_id")
            if status_val in ("excluded", "absent") and not (row.get("note") or "").strip():
                raise ArtifactContractError(f"catalog.csv 第 {i} 行：{status_val} 项 note 必填理由")
            rows.append({k: (row.get(k) or "").strip() for k in required})
    return rows
