# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""制作页需真实目录可达，QA 按完整资源身份而非同名文件计数。"""

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from auto_epublizer import orchestrator as orch
from auto_epublizer.fingerprint import generated_pages
from auto_epublizer.qa.provenance import audit_provenance

XHTML = "{http://www.w3.org/1999/xhtml}"
EPUB = "{http://www.idpf.org/2007/ops}"
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"


def _product(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# Chapter\n\nBody text.\n\n## Section\n\nSection body.\n", encoding="utf-8")
    store = orch.init(str(src), workspace_dir=str(tmp_path / "ws"))
    epub = orch.build(store)
    return store, epub


def test_production_page_is_top_level_in_both_navigations(tmp_path: Path) -> None:
    store, epub = _product(tmp_path)
    with zipfile.ZipFile(epub) as zf:
        page = next(iter(generated_pages(zf)))
        nav = ET.fromstring(zf.read("OEBPS/nav.xhtml"))
        toc = next(n for n in nav.iter(f"{XHTML}nav") if n.get(f"{EPUB}type") == "toc")
        top_links = toc.findall(f"{XHTML}ol/{XHTML}li/{XHTML}a")
        assert sum(a.get("href") == page for a in top_links) == 1
        ncx = ET.fromstring(zf.read("OEBPS/toc.ncx"))
        points = ncx.findall(f"{NCX}navMap/{NCX}navPoint")
        assert sum(p.find(f"{NCX}content").get("src") == page for p in points) == 1
        orders = [int(n.get("playOrder")) for n in ncx.iter(f"{NCX}navPoint")]
        assert orders == list(range(1, len(orders) + 1))
    result = audit_provenance(store, orch.structure_entries(store), epub, prefer_translation=False)
    assert result.ok, result.findings
    assert not result.toc_depth_mismatch


@pytest.mark.parametrize("document", ["nav.xhtml", "toc.ncx"])
def test_same_basename_wrong_directory_does_not_prove_production_access(
    tmp_path: Path, document: str
) -> None:
    store, epub = _product(tmp_path)
    bad = tmp_path / "bad.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(bad, "w") as dst:
        page = next(iter(generated_pages(src)))
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "OEBPS/" + document:
                data = data.replace(page.encode(), ("wrong/" + page).encode())
            dst.writestr(item, data)
    result = audit_provenance(store, orch.structure_entries(store), bad, prefer_translation=False)
    assert any(f["code"] == "E_TOC_PRODUCTION_TARGET" for f in result.findings)


def test_legacy_missing_production_entry_is_warning_not_source_unit_failure(tmp_path: Path) -> None:
    store, epub = _product(tmp_path)
    legacy = tmp_path / "legacy.epub"
    with zipfile.ZipFile(epub) as src, zipfile.ZipFile(legacy, "w") as dst:
        page = next(iter(generated_pages(src)))
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "OEBPS/nav.xhtml":
                data = re.sub(
                    r'<li><a href="' + re.escape(page) + r'">.*?</a></li>', "", data.decode()
                ).encode()
            elif item.filename == "OEBPS/toc.ncx":
                data = re.sub(
                    r'<navPoint\b[^>]*>\s*<navLabel>.*?</navLabel>\s*<content src="'
                    + re.escape(page)
                    + r'"/>\s*</navPoint>',
                    "",
                    data.decode(),
                    count=1,
                    flags=re.DOTALL,
                ).encode()
            dst.writestr(item, data)
    result = audit_provenance(
        store, orch.structure_entries(store), legacy, prefer_translation=False
    )
    assert result.ok, result.findings
    assert any(f["code"] == "W_TOC_PRODUCTION_MISSING" for f in result.findings)
