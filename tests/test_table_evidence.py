from zipfile import ZipFile

from typer.testing import CliRunner

from auto_epublizer.cli import app


def test_table_audit_locates_swapped_cells_under_multilevel_header(tmp_path):
    table = (
        '<table><caption>Results</caption><thead><tr><th colspan="2">kg</th></tr>'
        "<tr><th>East</th><th>West</th></tr></thead><tbody><tr><td>12</td><td>57</td></tr>"
        '</tbody><tfoot><tr><td colspan="2">Source: Ledger</td></tr></tfoot></table>'
    )
    expected = tmp_path / "table.xhtml"
    expected.write_text(table, encoding="utf-8")
    epub = tmp_path / "book.epub"
    member = "OEBPS/ch01.xhtml"
    with ZipFile(epub, "w") as zf:
        zf.writestr(member, table.replace("<td>12</td><td>57</td>", "<td>57</td><td>12</td>"))
    result = CliRunner().invoke(
        app, ["evidence", "table", str(expected), "--epub", str(epub), "--member", member]
    )
    assert result.exit_code == 1, result.output
    import json

    data = json.loads(result.stdout)
    assert [(f["row"], f["column"]) for f in data["findings"]] == [(3, 1), (3, 2)]
