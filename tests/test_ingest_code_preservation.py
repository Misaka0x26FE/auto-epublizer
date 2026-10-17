# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""代码围栏不得在进入渲染器前被误拆成章节或页码段。"""

from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch
from auto_epublizer.ingest.models import KIND_TEXT
from auto_epublizer.ingest.pandoc_reader import parse_markdown_units
from auto_epublizer.ingest.text_reader import read_text


@pytest.mark.parametrize("reader", ["text", "pandoc"])
@pytest.mark.parametrize(
    "opening,closing", [("```html", "```"), ("~~~", "~~~"), ("````", "````"), ("```{=html}", "```")]
)
def test_code_heading_and_blank_lines_survive_source_ingest(
    tmp_path: Path, reader: str, opening: str, closing: str
) -> None:
    code = f"{opening}\n<div>\n\n# not a chapter\nChapter 9 is code\n\n1\n\n</div>\n{closing}"
    markdown = f"# Real chapter\n\n{code}\n\n## Real subsection\nBody.\n"
    source = tmp_path / "source.md"
    source.write_text(markdown, encoding="utf-8")
    units = read_text(str(source)).units if reader == "text" else parse_markdown_units(markdown)
    assert [unit.title for unit in units] == ["Real chapter", "Real subsection"]
    assert [segment.source for segment in units[0].segments if segment.kind == KIND_TEXT] == [code]


def test_init_keeps_code_number_and_heading_in_original_unit(tmp_path: Path) -> None:
    code = "```html\n<div>\n\n## not a chapter\n\n1\n\n</div>\n```"
    source = tmp_path / "source.md"
    source.write_text(f"# Chapter I\n\n{code}\n\n## Real subsection\nBody.\n", encoding="utf-8")
    store = orch.init(str(source), workspace_dir=tmp_path / "workspace")
    publication = store.load_publication()
    assert [unit.title for unit in publication.units] == ["Chapter I", "Real subsection"]
    unit = publication.units[0]
    structured = (store.structured_dir / unit.meta["rel_path"]).read_text(encoding="utf-8")
    assert code in structured
