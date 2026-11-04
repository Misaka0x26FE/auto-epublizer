# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""排版样本册构建器（P1）。

把 ``tests/fixtures/typography/`` 的合成文本与生成图像，经**生产渲染链**
（``build.html.render_document`` → ``build.build_epub`` → ``pdfexport.render``）
组装为可重复的 EPUB/PDF，并提供：

- ``build_fixture_epub``：构建整册（可按主题、可做故障注入）；
- ``reconcile``：按 manifest 的期望对账结构、注释、图片与锚点；
- ``layout_digest``：与 git 状态无关的版式摘要（style.css 与内容摘要）；
- ``pdf_digest``：环境限定的 PDF 结构摘要（页数、文本摘要、Chromium 版本）。

样本全部为合成内容，不包含任何真实作品文本。
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import zipfile
import zlib
from pathlib import Path
from typing import Any

from auto_common.workspace import Publication, PublicationMeta, Unit
from auto_epublizer.build import build_epub
from auto_epublizer.build.html import (
    FootnoteState,
    NoteItem,
    NoteRef,
    render_document,
    subheading_anchors,
)
from auto_epublizer.fingerprint import strip_fingerprint_comments
from auto_epublizer.pdfexport import PrintStyle, find_chromium, render

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "typography"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
BASELINE_PATH = FIXTURE_DIR / "baseline.json"
FIXED_MODIFIED = "2026-01-01T00:00:00Z"


def load_manifest() -> dict[str, Any]:
    """读取样本册清单（唯一数据源：case/unit/期望/图像规格）。"""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _png(width: int, height: int, pattern: str) -> bytes:
    """生成确定性 PNG（RGB8，filter 0）；不依赖第三方库，仓库不存二进制。"""
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            if pattern == "gradient":
                v = x * 255 // max(1, width - 1)
                row += bytes((v, 60, 90))
            elif pattern == "noise":
                g = (x * 7 + y * 13) % 256
                row += bytes((g, g, g))
            else:
                row += bytes((30, 90, 140))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def fixture_media(manifest: dict[str, Any]) -> dict[str, bytes]:
    """按 manifest 规格生成全部媒体（EPUB 内路径 → 字节）。"""
    return {
        f"media/{name}": _png(spec["width"], spec["height"], spec["pattern"])
        for name, spec in manifest["media"].items()
    }


def iter_units(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """按阅读顺序展开 (case, unit) 对。"""
    cases = {case["case_id"]: case for case in manifest["cases"]}
    by_unit = {
        unit["unit_id"]: (case, unit) for case in manifest["cases"] for unit in case["units"]
    }
    order = manifest.get("reading_order") or list(by_unit)
    units: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for unit_id in order:
        if unit_id not in by_unit:
            raise KeyError(f"reading_order 引用了未定义的 unit：{unit_id}")
        units.append(by_unit[unit_id])
    if len(units) != sum(len(case["units"]) for case in cases.values()):
        raise ValueError("reading_order 必须覆盖 manifest 中全部 unit")
    return units


def unit_markdown(unit: dict[str, Any]) -> str:
    return (FIXTURE_DIR / unit["markdown"]).read_text(encoding="utf-8")


def _note_render_args(unit: dict[str, Any]) -> dict[str, Any]:
    """结构化注释（N 阶段）渲染参数：ref → note 绑定与宿主回链。"""
    cfg = unit.get("notes")
    if not cfg:
        return {}
    host = f"{unit['unit_id']}.xhtml"
    refs: dict[str, NoteRef] = {}
    items: list[NoteItem] = []
    for item in cfg["items"]:
        items.append(
            NoteItem(
                note_id=item["note_id"],
                number=item["number"],
                text_md=item["text_md"],
                backlinks=tuple(f"{host}#{ref}" for ref in item["refs"]),
            )
        )
        for ref in item["refs"]:
            refs[ref] = NoteRef(ref_id=ref, note_id=item["note_id"], number=item["number"])
    return {"note_refs": refs, "note_items": items, "href_by_note": {}}


def render_unit(unit: dict[str, Any], *, lang: str, drop_aside: str | None = None) -> str:
    """渲染一个单元为 XHTML；``drop_aside`` 用于故障注入（删掉注文保 noteref）。"""
    html = render_document(
        unit["title"],
        unit_markdown(unit),
        lang=lang,
        unit_id=unit["unit_id"],
        fn_state=FootnoteState(),
        role=unit.get("role", ""),
        **_note_render_args(unit),
    )
    if drop_aside:
        html = re.sub(
            rf'<aside[^>]*id="fn-{re.escape(drop_aside)}".*?</aside>',
            "",
            html,
            flags=re.S,
        )
    return html


def _entry(unit: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": unit["unit_id"],
        "kind": unit["kind"],
        "region": unit["region"],
        "title": unit["title"],
        "level": unit.get("level", 1),
        "anchors": subheading_anchors(unit_markdown(unit), unit["unit_id"]),
    }


def build_fixture_epub(
    tmp_path: Path,
    manifest: dict[str, Any] | None = None,
    *,
    theme: str = "standard",
    drop_media: str | None = None,
    drop_aside: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """用生产构建链生成整册 EPUB；返回路径、清单、各单元 XHTML 与媒体。"""
    manifest = manifest or load_manifest()
    lang = manifest["book"]["lang"]
    units = iter_units(manifest)
    media = fixture_media(manifest)
    if drop_media:
        media.pop(f"media/{drop_media}", None)
    content_files = [
        (f"{unit['unit_id']}.xhtml", render_unit(unit, lang=lang, drop_aside=drop_aside))
        for _case, unit in units
    ]
    pub = Publication(
        slug=manifest["book"]["slug"],
        meta=PublicationMeta(
            title=manifest["book"]["title"],
            creator=manifest["book"]["creator"],
            target_language=lang,
        ),
        units=[
            Unit(id=unit["unit_id"], kind=unit["kind"], title=unit["title"])
            for _case, unit in units
        ],
    )
    out = tmp_path / (name or "typography-samples.epub")
    build_epub(
        pub,
        [_entry(unit) for _case, unit in units],
        content_files,
        lang=lang,
        modified=FIXED_MODIFIED,
        out_path=out,
        media_files=list(media.items()),
        theme=theme,
        cover_media="media/cover.png",
        nav_depth=3,
        render_mode="translation",
    )
    return {
        "epub": out,
        "manifest": manifest,
        "content": dict(content_files),
        "media": media,
        "theme": theme,
    }


_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
#: 制作声明含 revision/dirty/工具版本，跨提交必然变化，不属于版式
_PROVENANCE_RE = re.compile(r'<section class="software-provenance">.*?</section>', re.S)
#: 印刷文本层中的构建身份行：归一化后片段不随提交变化
_REVISION_RE = re.compile(r"Revision: [0-9a-f]{7,64}(?: \(modified source\))?")


def _visible_text(xhtml: str) -> str:
    return _TAG_RE.sub("", _COMMENT_RE.sub("", xhtml))


def reconcile(epub_path: Path, manifest: dict[str, Any] | None = None) -> list[str]:
    """按 manifest 对账成品：文件在包、标记可读、注释成对、图片有字节、锚点不悬空。"""
    manifest = manifest or load_manifest()
    problems: list[str] = []
    with zipfile.ZipFile(epub_path) as zf:
        names = set(zf.namelist())
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        for _case, unit in iter_units(manifest):
            unit_id = unit["unit_id"]
            member = f"OEBPS/{unit_id}.xhtml"
            if member not in names:
                problems.append(f"{unit_id}: 内容文档缺失")
                continue
            xhtml = zf.read(member).decode("utf-8")
            text = _visible_text(xhtml)
            expect = unit["expect"]
            for marker in expect.get("markers", []):
                if marker not in text:
                    problems.append(f"{unit_id}: 缺少标记 {marker}")
            refs = xhtml.count('epub:type="noteref"')
            asides = xhtml.count("<aside")
            if refs != expect.get("noterefs", 0):
                problems.append(f"{unit_id}: noteref 期望 {expect.get('noterefs', 0)} 实际 {refs}")
            if asides != expect.get("asides", 0):
                problems.append(f"{unit_id}: aside 期望 {expect.get('asides', 0)} 实际 {asides}")
            for image in expect.get("images", []):
                if f"media/{image}" not in xhtml:
                    problems.append(f"{unit_id}: 未引用图片 {image}")
                if f"OEBPS/media/{image}" not in names:
                    problems.append(f"{unit_id}: 图片字节缺失 media/{image}")
            for selector in expect.get("selectors", []):
                if selector not in xhtml:
                    problems.append(f"{unit_id}: 缺少结构 {selector}")
            if unit["kind"] != "cover" and f"{unit_id}.xhtml" not in nav:
                problems.append(f"{unit_id}: 未进入目录")
            for anchor in subheading_anchors(unit_markdown(unit), unit_id):
                if f'id="{anchor["anchor"]}"' not in xhtml:
                    problems.append(f"{unit_id}: 目录锚点悬空 {anchor['anchor']}")
    return problems


def layout_digest(epub_path: Path) -> dict[str, Any]:
    """与 git 版本/构建时间无关的版式摘要（用于 P2 等价与 P3+ 前后对照）。

    剔除两类非版式内容：构建指纹注释，以及可见的 ``software-provenance`` 制作声明
    （其中含 revision/dirty/工具版本，跨提交必然变化）。样本正文、语义结构、媒体与
    ``style.css`` 全部参与摘要。
    """
    with zipfile.ZipFile(epub_path) as zf:
        style = zf.read("OEBPS/style.css")
        documents = {
            name: _PROVENANCE_RE.sub("", strip_fingerprint_comments(zf.read(name).decode("utf-8")))
            for name in sorted(zf.namelist())
            if name.startswith("OEBPS/") and name.endswith(".xhtml")
        }
        media = {
            name: hashlib.sha256(zf.read(name)).hexdigest()
            for name in sorted(zf.namelist())
            if name.startswith("OEBPS/media/")
        }
    joined = "\n".join(f"{name}\0{text}" for name, text in sorted(documents.items()))
    return {
        "style_sha256": hashlib.sha256(style).hexdigest(),
        "style_bytes": len(style),
        "content_sha256": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
        "documents": len(documents),
        "media": media,
    }


def chromium_version(browser: str) -> str:
    try:
        proc = subprocess.run([browser, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 环境相关
        return f"unknown ({exc.__class__.__name__})"
    return (proc.stdout or proc.stderr).strip()


def pdf_digest(epub_path: Path, out_path: Path) -> dict[str, Any]:
    """渲染 PDF 并返回结构摘要（页数/文本摘要/纸张/环境）；无 Chromium 时由调用方跳过。

    文本摘要前把制作声明里的 ``Revision: <sha> (modified source)`` 归一化：构建身份
    随提交变化，不属于版式基线（与 EPUB 摘要剔除 provenance 同一口径）。
    """
    import pymupdf

    result = render(epub_path, out_path, PrintStyle())
    with pymupdf.open(result.out) as doc:
        text = "\n".join(page.get_text("text") for page in doc)
        sizes = sorted({(round(page.rect.width, 1), round(page.rect.height, 1)) for page in doc})
    text = _REVISION_RE.sub("Revision: <normalized>", text)
    browser = find_chromium() or ""
    return {
        "pages": result.pages,
        "text_chars": len(text),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "page_boxes_pt": [list(size) for size in sizes],
        "size_mm": list(result.size_mm),
        "chromium": chromium_version(browser) if browser else "missing",
        "pymupdf": pymupdf.__version__,
        "pdf_sha256": hashlib.sha256(result.out.read_bytes()).hexdigest(),
    }
