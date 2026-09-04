"""插入内容（插图/表格/公式）描述文件：structured/raw/inserts/。

每个插入内容一份 ``<id>.json``（CLI 生成确定性字段，agent 补语义字段）+
``index.jsonl`` 汇总索引（按 id 排序）。schema 与溯源规范见
docs/pdf-content-spec.md §2。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

INSERT_KINDS = {"image": "img", "table": "tbl", "formula": "fml"}


class InsertSource(BaseModel):
    """插入内容的原始内容地址（溯源到源文件的唯一依据）。"""

    page: int  # 源页号（1-based）
    bbox: list[float] | None = None  # 页内坐标 [x0, y0, x1, y1]
    xref: int | None = None  # PDF 对象号（内嵌图必填；区域/整页可为 None）
    method: str  # embedded | full_page | crop | table | formula


class InsertRecord(BaseModel):
    """一个插入内容（图/表/公式）的描述记录。"""

    id: str  # p{page:03d}-{img|tbl|fml}{nn:02d}
    type: str  # image | table | formula
    source: InsertSource
    file: str | None = None  # 相对 structured/raw/ 的媒体路径；纯文本表格为 None
    markdown: str | None = None  # 纯文本表格的自包含 md；其余为 None
    content_desc: str = ""  # agent 补：这个插入内容讲什么
    latex: str | None = None  # formula：agent 手写 LaTeX；其余为 None
    extra: dict = Field(default_factory=dict)  # 保留扩展位


def next_insert_id(records: list[InsertRecord], page: int, type_: str) -> str:
    """生成页内递增的插入内容 id（确定性：已有多少同类即 +1）。"""
    kind = INSERT_KINDS[type_]
    prefix = f"p{page:03d}-{kind}"
    return f"{prefix}{sum(1 for r in records if r.id.startswith(prefix)) + 1:02d}"


def write_inserts(raw_dir: Path, records: list[InsertRecord]) -> None:
    """落盘 raw/inserts/<id>.json + index.jsonl（按 id 排序；幂等覆盖）。"""
    if not records:
        return
    out = Path(raw_dir) / "inserts"
    out.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: r.id)
    for r in ordered:
        (out / f"{r.id}.json").write_text(
            json.dumps(r.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (out / "index.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in ordered),
        encoding="utf-8",
    )


def read_inserts(raw_dir: Path) -> list[InsertRecord]:
    """读取 index.jsonl（缺目录/文件返回空表；坏行跳过）。"""
    idx = Path(raw_dir) / "inserts" / "index.jsonl"
    if not idx.is_file():
        return []
    out: list[InsertRecord] = []
    for line in idx.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(InsertRecord.model_validate_json(line))
        except ValueError:
            continue
    return out
