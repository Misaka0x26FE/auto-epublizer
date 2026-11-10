"""表格双路径测试：md 生成（纯函数）+ 实 PDF 检测（画线表格）。"""

from __future__ import annotations

from auto_epublizer.ingest.tables import table_to_markdown


def test_table_to_markdown_basic() -> None:
    md = table_to_markdown([["a", "b"], ["1", "2"]])
    assert md == "| a | b |\n| --- | --- |\n| 1 | 2 |"


def test_table_to_markdown_pads_and_escapes() -> None:
    md = table_to_markdown([["h1", "h2", None], ["x|y", "z"]])
    lines = md.splitlines()
    assert lines[0] == "| h1 | h2 |  |"
    assert lines[1] == "| --- | --- | --- |"
    assert "\\|y" in lines[2]


def test_table_to_markdown_empty_returns_none() -> None:
    assert table_to_markdown([[None, ""], [None, None]]) is None
    assert table_to_markdown([]) is None


def test_table_to_markdown_collapses_newlines() -> None:
    md = table_to_markdown([["h"], ["multi\nline"]])
    assert "| multi line |" in md


def test_extract_tables_rejects_oversized_cells(tmp_path) -> None:
    """单格超长 → 版面误检（整页吞进一格），放弃记录（真书 dogfooding 回归）。"""
    import fitz

    from auto_epublizer.ingest.inserts import InsertRecord
    from auto_epublizer.ingest.tables import extract_tables

    pdf = fitz.open()
    page = pdf.new_page()
    _draw_table(page, 200, 200, 500, 320)
    long_text = "很长的一段正文。" * 40  # 单格 > 300 字符
    page.insert_text((210, 235), long_text[:80], fontsize=9)
    page.insert_text((210, 255), long_text[80:160], fontsize=9)
    pdf_path = tmp_path / "big.pdf"
    pdf.save(str(pdf_path))
    pdf.close()

    doc = fitz.open(str(pdf_path))
    records: list[InsertRecord] = []
    blocks = extract_tables(
        doc[0],
        records=records,
        media_dir=tmp_path / "media",
        image_bboxes=[],
        formula_bboxes=[],
    )
    doc.close()
    if blocks:
        assert all(
            max(len((c or "").strip()) for row in [b.get("markdown", "").split("|")] for c in row)
            <= 300
            for b in blocks
        )
    # 无论如何不应产出带超长单元格的 md 记录
    assert all(
        r.markdown is None or len(max(r.markdown.split("|"), key=len)) <= 300 for r in records
    )


def _draw_table(page, x0, y0, x1, y1) -> None:
    """画一个 2x2 带线表格边框（供 find_tables lines 策略检出）。"""
    mid_x = (x0 + x1) / 2
    mid_y = (y0 + y1) / 2
    for yy in (y0, mid_y, y1):
        page.draw_line((x0, yy), (x1, yy), color=(0, 0, 0), width=0.7)
    for xx in (x0, mid_x, x1):
        page.draw_line((xx, y0), (xx, y1), color=(0, 0, 0), width=0.7)


def test_find_tables_on_drawn_grid(tmp_path) -> None:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    _draw_table(page, 200, 200, 500, 320)
    page.insert_text((230, 235), "head a", fontsize=11)
    page.insert_text((370, 235), "head b", fontsize=11)
    page.insert_text((230, 295), "v1", fontsize=11)
    page.insert_text((370, 295), "v2", fontsize=11)
    pdf_path = tmp_path / "tbl.pdf"
    pdf.save(str(pdf_path))
    pdf.close()

    doc = fitz.open(str(pdf_path))
    tables = doc[0].find_tables().tables
    assert len(tables) >= 1
    md = table_to_markdown(tables[0].extract())
    assert md is not None and "head a" in md and "v2" in md
    doc.close()


def test_extract_tables_markdown_path_writes_record(tmp_path) -> None:
    import fitz

    from auto_epublizer.ingest.inserts import read_inserts
    from auto_epublizer.ingest.tables import extract_tables

    pdf = fitz.open()
    page = pdf.new_page()
    _draw_table(page, 200, 200, 500, 320)
    page.insert_text((230, 235), "head a", fontsize=11)
    page.insert_text((370, 235), "head b", fontsize=11)
    pdf_path = tmp_path / "tbl.pdf"
    pdf.save(str(pdf_path))
    pdf.close()

    doc = fitz.open(str(pdf_path))
    records: list = []
    media_dir = tmp_path / "media"
    blocks = extract_tables(
        doc[0], records=records, media_dir=media_dir, image_bboxes=[], formula_bboxes=[]
    )
    doc.close()
    assert len(blocks) == 1
    b = blocks[0]
    assert b["type"] == "table" and b["markdown"] and "head a" in b["markdown"]
    assert b["file"] is None and "| head a" in b["text"]
    recs = records or read_inserts(tmp_path)
    assert len(recs) == 1
    assert recs[0].type == "table" and recs[0].source.method == "table"
    assert recs[0].markdown == b["markdown"] and recs[0].file is None


def test_table_cell_strips_pollution_atx_marker() -> None:
    """B4：PDF 抽取把标题层级带进单元格时，渲染层去掉 ATX 标记。"""
    from auto_epublizer.build.html import markdown_to_xhtml

    html = markdown_to_xhtml("| **## 小节标题** | |\n|---|---|\n| a | b |\n")
    assert "<strong>小节标题</strong>" in html
    assert "## 小节标题" not in html


def test_table_cell_keeps_literal_hashes_and_code() -> None:
    """合法编号、C#、行内代码里的井号原样保留。"""
    from auto_epublizer.build.html import markdown_to_xhtml

    html = markdown_to_xhtml("| # 1 | C# | `## x` |\n|---|---|---|\n| a | b | c |\n")
    assert "# 1" in html
    assert "C#" in html
    assert "## x" in html  # 代码内容
    assert "<code>" in html


def test_cell_atx_detector_flags_only_non_code_non_number() -> None:
    """检测口独立于渲染：代码、合法编号不报，污染形态报候选。"""
    from auto_epublizer.qa.audit import AuditResult, _cell_atx_candidates

    dirty = AuditResult(ok=True)
    _cell_atx_candidates(
        dirty, "ch01.xhtml", "<table><tr><td><strong>## 标题</strong></td></tr></table>"
    )
    assert [f.code for f in dirty.findings] == ["W_CELL_ATX"]

    for clean in (
        "<td><code>## x</code></td>",
        "<td># 1</td>",
        "<td>C#</td>",
        "<td>普通文本</td>",
    ):
        result = AuditResult(ok=True)
        _cell_atx_candidates(result, "ch01.xhtml", f"<table><tr>{clean}</tr></table>")
        assert result.findings == [], clean
