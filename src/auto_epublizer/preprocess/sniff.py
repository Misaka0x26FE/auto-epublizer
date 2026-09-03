"""源文件内容嗅探（确定性、零 token）：类型判定 + 元数据 + TOC + 体检信号。

按扩展名分发，直读源文件（zipfile/fitz/正则），不经 ingest reader：
- EPUB：zip 解析 container/OPF（DC 元数据）、nav/NCX（TOC）、encryption.xml（DRM）
- PDF：pymupdf metadata / get_toc / 逐页文字层比例 / 乱码率（替换字符）
- DOCX：zip 读 docProps/core.xml（DC 元数据）
- HTML：`<title>` 与 og: meta、lang 属性
- TXT/MD：无内部元数据，规模由 facts 层统计
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

_DC = "http://purl.org/dc/elements/1.1/"
_OPF = "http://www.idpf.org/2007/opf"

_SUPPORTED = {".txt", ".md", ".markdown", ".html", ".htm", ".xhtml", ".docx", ".epub", ".pdf"}


class SniffError(ValueError):
    """无法嗅探的输入（不支持格式/损坏文件）。"""


def _detect_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in _SUPPORTED:
        raise SniffError(f"不支持的格式：{ext}（支持 {' '.join(sorted(_SUPPORTED))}）")
    return {".md": "md", ".markdown": "md", ".htm": "html", ".xhtml": "html"}.get(
        ext, ext.lstrip(".")
    )


def sniff_epub(path: Path) -> dict[str, Any]:
    """EPUB 嗅探：DRM / DC 元数据 / TOC（nav 优先，NCX 兜底）/ spine 数。"""
    facts: dict[str, Any] = {
        "kind": "epub",
        "drm": False,
        "metadata": {},
        "toc": [],
        "spine_count": 0,
    }
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise SniffError(f"EPUB 不是有效的 zip：{e}") from e
    with zf:
        names = zf.namelist()
        # DRM：加密描述文件存在即视为有保护
        if any(n.lower() == "meta-inf/encryption.xml" for n in names):
            facts["drm"] = True
        # container → OPF
        try:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            opf_path = rootfile.get("full-path") if rootfile is not None else None
        except ET.ParseError:
            opf_path = None
        if opf_path and opf_path in names:
            try:
                opf = ET.fromstring(zf.read(opf_path))
                md = opf.find(".//{*}metadata")
                meta: dict[str, str] = {}
                if md is not None:
                    for tag in ("title", "creator", "language", "date", "identifier", "publisher"):
                        el = md.find(f"{{{_DC}}}{tag}")
                        if el is not None and (el.text or "").strip():
                            meta[tag] = el.text.strip()
                facts["metadata"] = meta
                spine = opf.findall(".//{*}spine/{*}itemref")
                facts["spine_count"] = len(spine)
                # TOC：EPUB3 nav（properties 含 nav）；EPUB2 NCX 兜底
                nav_href = None
                for item in opf.findall(".//{*}manifest/{*}item"):
                    if "nav" in (item.get("properties") or ""):
                        nav_href = item.get("href")
                        break
                opf_dir = Path(opf_path).parent
                if nav_href:
                    nav_full = (opf_dir / nav_href).as_posix()
                    if nav_full in names:
                        facts["toc"] = _parse_nav_toc(zf.read(nav_full).decode("utf-8", "ignore"))
                if not facts["toc"]:
                    ncx_href = next(
                        (
                            i.get("href")
                            for i in opf.findall(".//{*}manifest/{*}item")
                            if (i.get("media-type") or "") == "application/x-dtbncx+xml"
                        ),
                        None,
                    )
                    if ncx_href:
                        ncx_full = (opf_dir / ncx_href).as_posix()
                        if ncx_full in names:
                            facts["toc"] = _parse_ncx_toc(
                                zf.read(ncx_full).decode("utf-8", "ignore")
                            )
            except ET.ParseError:
                pass
    return facts


def _parse_nav_toc(xhtml: str) -> list[dict[str, str]]:
    """解析 EPUB3 nav TOC：<nav epub:type="toc"> 下的 <a>（文本 + href）。"""
    try:
        root = ET.fromstring(xhtml)
    except ET.ParseError:
        return []
    out: list[dict[str, str]] = []
    for nav in root.iter("{http://www.w3.org/1999/xhtml}nav"):
        if "toc" in (nav.get("{http://www.idpf.org/2007/ops}type") or ""):
            for a in nav.iter("{http://www.w3.org/1999/xhtml}a"):
                title = "".join(a.itertext()).strip()
                href = (a.get("href") or "").split("#")[0]
                if title and href:
                    out.append({"title": title, "href": href})
            break
    return out


def _parse_ncx_toc(ncx: str) -> list[dict[str, str]]:
    """解析 EPUB2 NCX：navPoint 的 navLabel/text 与 content/src。"""
    try:
        root = ET.fromstring(ncx)
    except ET.ParseError:
        return []
    out: list[dict[str, str]] = []
    for np in root.iter("{http://www.daisy.org/z3986/2005/ncx/}navPoint"):
        label = np.find(
            "{http://www.daisy.org/z3986/2005/ncx/}navLabel/"
            "{http://www.daisy.org/z3986/2005/ncx/}text"
        )
        content = np.find("{http://www.daisy.org/z3986/2005/ncx/}content")
        if label is not None and content is not None:
            title = (label.text or "").strip()
            href = (content.get("src") or "").split("#")[0]
            if title and href:
                out.append({"title": title, "href": href})
    return out


def sniff_pdf(path: Path) -> dict[str, Any]:
    """PDF 嗅探：文字层比例（扫描件判定）/ 乱码率 / 元数据 / bookmark TOC / 页数。"""
    import fitz  # pymupdf

    try:
        doc = fitz.open(str(path))
    except Exception as e:  # noqa: BLE001
        raise SniffError(f"无法打开 PDF：{e}") from e
    page_count = doc.page_count
    # 逐页统计（>500 页时每 5 页抽样，控时）
    step = 5 if page_count > 500 else 1
    total = 0
    empty_pages = 0
    garbled_chars = 0
    sample_chars = 0
    for i in range(0, page_count, step):
        text = doc[i].get_text().strip()
        sample_chars += len(text)
        total += 1
        if not text:
            empty_pages += 1
        garbled_chars += text.count("\ufffd")
    doc.close()

    # fitz.open 需再次取 metadata/toc
    try:
        doc = fitz.open(str(path))
        meta_raw = doc.metadata or {}
        toc = [{"level": lvl, "title": title, "page": page} for lvl, title, page in doc.get_toc()]
        doc.close()
    except Exception:  # noqa: BLE001
        meta_raw, toc = {}, []

    meta = {k: str(v).strip() for k, v in meta_raw.items() if v}
    garbled_ratio = round(garbled_chars / sample_chars, 4) if sample_chars else 0.0
    empty_ratio = round(empty_pages / total, 4) if total else 1.0
    return {
        "kind": "pdf",
        "page_count": page_count,
        # 文字层判定：抽样页无文字比例 > 60% → 扫描件；部分有 → 混合
        "has_text_layer": empty_ratio < 0.6 and sample_chars > 0,
        "scanned": empty_ratio >= 0.6,
        "empty_text_ratio": empty_ratio,
        "garbled_ratio": garbled_ratio,
        "metadata": {
            "title": meta.get("title", ""),
            "creator": meta.get("author", ""),
            "date": meta.get("creationDate", ""),
            "producer": meta.get("producer", ""),
        },
        "toc": toc,
    }


def sniff_docx(path: Path) -> dict[str, Any]:
    """DOCX 嗅探：docProps/core.xml 的 DC 元数据。"""
    meta: dict[str, str] = {}
    try:
        with zipfile.ZipFile(path) as zf:
            if "docProps/core.xml" in zf.namelist():
                root = ET.fromstring(zf.read("docProps/core.xml"))
                _NS = {
                    "dc": _DC,
                    "dcterms": "http://purl.org/dc/terms/",
                    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
                }
                for tag, ns in (("title", "dc"), ("creator", "dc"), ("language", "dc")):
                    el = root.find(f"{ns}:{tag}", _NS)
                    if el is not None and (el.text or "").strip():
                        meta[tag] = el.text.strip()
                for tag in ("created", "modified"):
                    el = root.find(f"dcterms:{tag}", _NS)
                    if el is not None and (el.text or "").strip() and "date" not in meta:
                        meta["date"] = el.text.strip()
    except (zipfile.BadZipFile, ET.ParseError):
        pass
    return {"kind": "docx", "metadata": meta}


def sniff_html(path: Path) -> dict[str, Any]:
    """HTML 嗅探：<title>、og: meta、html lang。"""
    text = path.read_text(encoding="utf-8", errors="replace")[:200_000]
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    lang_m = re.search(r"<html[^>]*\blang=[\"']([^\"']+)[\"']", text, re.IGNORECASE)
    og: dict[str, str] = {}
    for m in re.finditer(
        r"<meta[^>]+property=[\"'](og:[\w-]+)[\"'][^>]+content=[\"']([^\"']*)[\"']",
        text,
        re.IGNORECASE,
    ):
        og[m.group(1)] = m.group(2).strip()
    meta: dict[str, str] = {}
    if title_m and title_m.group(1).strip():
        meta["title"] = title_m.group(1).strip()
    if lang_m:
        meta["language"] = lang_m.group(1).strip()
    if og.get("og:title"):
        meta.setdefault("title", og["og:title"])
    if og.get("og:description"):
        meta["description"] = og["og:description"]
    return {"kind": "html", "metadata": meta}


def sniff(path: str | Path) -> dict[str, Any]:
    """分发嗅探：按扩展名调用对应探测器，返回统一 facts 字典。"""
    p = Path(path)
    if not p.is_file():
        raise SniffError(f"源文件不存在：{p}")
    kind = _detect_kind(p)
    if kind == "epub":
        return sniff_epub(p)
    if kind == "pdf":
        return sniff_pdf(p)
    if kind == "docx":
        return sniff_docx(p)
    if kind in ("html",):
        return sniff_html(p)
    return {"kind": kind, "metadata": {}}
