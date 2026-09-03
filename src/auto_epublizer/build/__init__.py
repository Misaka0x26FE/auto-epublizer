"""EPUB 3 打包：把结构化单元 XHTML + 媒体资源封装为确定性标准 EPUB。

- 纯 Python 直写 zip（mimetype 首位未压缩），不依赖 pandoc/calibre。
- 组件：mimetype / META-INF/container.xml / OEBPS/content.opf / nav.xhtml /
  toc.ncx / landmarks.xhtml + 内容文档 + 媒体资源。
- 确定性：冻结时间戳（``modified`` 参数）+ 稳定写入顺序 → 同一工作区两次构建字节一致。
- 元数据一律 XML 转义，含特殊字符的书名/作者不会破坏任意 XML 文档。
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from auto_common.workspace import Publication

from .html import slug_file

_IMG_REF = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# pandoc 对「段落内仅一张图片」输出占位语法（小说插图常见形态）：
#   [alt]{.image .placeholder original-image-src="media/x.png" original-image-title="..."}
_PANDOC_PLACEHOLDER = re.compile(
    r"\[([^\]]*)\]\{\.image\s+\.placeholder\s+original-image-src=\"([^\"]+)\""
    r"(?:\s+original-image-title=\"[^\"]*\")?\s*\}"
)
# HTML <img> 及其可能的 <figure>/<a> 包裹（多行可匹配）：
#   <figure ...><a ...><img src="..." .../></a></figure>
_HTML_FIG_IMG = re.compile(
    r"<figure\b[^>]*>\s*<a\b[^>]*>\s*<img\b[^>]*?src=\"([^\"]+)\"[^>]*?/?>\s*</a>\s*</figure>",
    re.DOTALL,
)
_HTML_IMG = re.compile(r"<img\b[^>]*?src=\"([^\"]+)\"[^>]*?/?>", re.DOTALL)

# 内置基础样式：正文可读性（行距/段距/两端对齐）、标题居中、图片限宽居中。
_STYLE_CSS = """\
body {
  font-family: Georgia, \"Noto Serif CJK SC\", \"Source Han Serif SC\", serif;
  line-height: 1.9;
  margin: 4% 5%;
}
h1 {
  text-align: center;
  margin: 1.6em 0 1.2em;
  font-size: 1.45em;
  line-height: 1.5;
}
h2, h3, h4, h5, h6 {
  text-align: center;
  margin: 1.4em 0 1em;
}
p {
  margin: 0 0 0.9em 0;
  text-align: justify;
  text-indent: 2em; /* 中文正文首行缩进两字 */
}
p.imgp {
  text-indent: 0;
  text-align: center; /* 图片段居中、不缩进 */
}
img {
  max-width: 100%;
  height: auto;
}
strong {
  font-weight: bold;
}
em {
  font-style: italic;
}
"""

_NS_XHTML = "http://www.w3.org/1999/xhtml"
_NS_EPUB = "http://www.idpf.org/2007/ops"
_NS_OPF = "http://www.idpf.org/2007/opf"
_NS_DC = "http://purl.org/dc/elements/1.1/"

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


def _parse_modified(modified: str) -> tuple[int, int, int, int, int, int]:
    """把 ISO 时间戳解析为 zipfile date_time 元组（缺省回退 1970 基准）。"""
    try:
        dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
        return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    except ValueError:
        return (1970, 1, 1, 0, 0, 0)


def _zi(name: str, ts: tuple[int, int, int, int, int, int], compress: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ts)
    info.compress_type = compress
    return info


def _content_entries(
    entries: list[dict[str, Any]], content_files: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    """只保留已实际生成内容文档的条目（nav/spine 不得引用缺失文件）。"""
    present = {fn for fn, _ in content_files}
    return [e for e in entries if f"{slug_file(e['id'])}.xhtml" in present]


def _render_opf(
    pub: Publication,
    lang: str,
    modified: str,
    items: list[tuple[str, str, str, str | None]],
    spine_ids: list[str],
) -> str:
    """渲染 content.opf：manifest / spine / DC 元数据 / dcterms:modified。"""
    ident = pub.meta.identifier
    uid = ident.isbn or ident.uri or ident.doi or pub.slug
    meta = pub.meta
    m = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<package xmlns="{_NS_OPF}" version="3.0" unique-identifier="pub-id">',
        f'  <metadata xmlns:dc="{_NS_DC}">',
        f'    <dc:identifier id="pub-id">{escape(uid)}</dc:identifier>',
        f"    <dc:title>{escape(meta.title)}</dc:title>",
    ]
    if meta.creator:
        m.append(f"    <dc:creator>{escape(meta.creator)}</dc:creator>")
    m.append(f"    <dc:language>{escape(lang)}</dc:language>")
    if meta.date:
        m.append(f"    <dc:date>{escape(meta.date)}</dc:date>")
    if meta.publisher:
        m.append(f"    <dc:publisher>{escape(meta.publisher)}</dc:publisher>")
    if meta.rights:
        m.append(f"    <dc:rights>{escape(meta.rights)}</dc:rights>")
    m.append(f'    <meta property="dcterms:modified">{escape(modified)}</meta>')
    m.append("  </metadata>")
    m.append("  <manifest>")
    for item_id, href, media_type, props in items:
        prop_attr = f' properties="{escape(props)}"' if props else ""
        m.append(
            f'    <item id="{escape(item_id)}" href="{escape(href)}" '
            f'media-type="{escape(media_type)}"{prop_attr}/>'
        )
    m.append("  </manifest>")
    m.append("  <spine>")
    for rid in spine_ids:
        m.append(f'    <itemref idref="{escape(rid)}"/>')
    m.append("  </spine>")
    m.append("</package>")
    return "\n".join(m)


def _render_nav(
    pub: Publication,
    entries: list[dict[str, Any]],
    content_entries: list[dict[str, Any]],
    lang: str,
) -> str:
    """渲染 EPUB 3 导航文档（nav.xhtml，epub:type=toc）。"""
    items = []
    for e in content_entries:
        href = f"{slug_file(e['id'])}.xhtml"
        items.append(
            f'        <li><a href="{escape(href)}">{escape(e["title"] or e["id"])}</a></li>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="{_NS_XHTML}" xmlns:epub="{_NS_EPUB}" '
        f'xml:lang="{escape(lang, quote=True)}">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        f"<title>{escape(pub.meta.title)}</title>\n"
        "</head>\n"
        "<body>\n"
        f'<nav epub:type="toc" id="toc">\n'
        "  <h1>目录</h1>\n"
        "  <ol>\n"
        f"{chr(10).join(items)}\n"
        "  </ol>\n"
        "</nav>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_ncx(
    pub: Publication,
    entries: list[dict[str, Any]],
) -> str:
    """渲染 NCX（toc.ncx，向后兼容）；navPoint + playOrder 扁平目录（覆盖全部条目）。"""
    uid = pub.slug
    points = []
    for order, e in enumerate(entries, start=1):
        href = f"{slug_file(e['id'])}.xhtml"
        label = e["title"] or e["id"]
        points.append(
            "    <navPoint id="
            f'"navpoint-{order}" playOrder="{order}">\n'
            f"      <navLabel><text>{escape(label)}</text></navLabel>\n"
            f'      <content src="{escape(href)}"/>\n'
            "    </navPoint>"
        )
    body = "\n".join(points)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        "  <head>\n"
        f'    <meta name="dtb:uid" content="{escape(uid)}"/>\n'
        '    <meta name="dtb:depth" content="1"/>\n'
        '    <meta name="dtb:totalPageCount" content="0"/>\n'
        '    <meta name="dtb:maxPageNumber" content="0"/>\n'
        "  </head>\n"
        f"  <docTitle><text>{escape(pub.meta.title)}</text></docTitle>\n"
        "  <navMap>\n"
        f"{body}\n"
        "  </navMap>\n"
        "</ncx>\n"
    )


def _render_landmarks(
    entries: list[dict[str, Any]],
    lang: str,
) -> str:
    """渲染 landmarks（frontmatter / bodymatter / backmatter 地标）。

    为每个出现的 region 无条件生成一条地标（不依赖内容文件是否已生成），
    确保 frontmatter/bodymatter/backmatter 三类地标始终可用。
    """
    landmarks: list[tuple[str, str, str]] = []
    labels = {
        "frontmatter": "前言",
        "bodymatter": "正文",
        "backmatter": "附录",
    }
    for region in ("frontmatter", "bodymatter", "backmatter"):
        for e in entries:
            raw = e.get("region")
            if raw == "body":
                raw = "bodymatter"
            if raw != region:
                continue
            href = f"{slug_file(e['id'])}.xhtml"
            landmarks.append((region, href, labels[region]))
            break
    lis = []
    for etype, href, label in landmarks:
        lis.append(
            f'      <li><a epub:type="{etype}" href="{escape(href)}">{escape(label)}</a></li>'
        )
    lis_html = "\n".join(lis) if lis else "      <!-- 无可落地标的条目 -->"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="{_NS_XHTML}" xmlns:epub="{_NS_EPUB}" '
        f'xml:lang="{escape(lang, quote=True)}">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        "<title>地标</title>\n"
        "</head>\n"
        "<body>\n"
        '<nav epub:type="landmarks" id="landmarks">\n'
        "  <ol>\n"
        f"{lis_html}\n"
        "  </ol>\n"
        "</nav>\n"
        "</body>\n"
        "</html>\n"
    )


def collect_media(md_text: str, media_root: str | Path) -> tuple[str, list[tuple[str, bytes]]]:
    """改写 md 中图片引用为 EPUB 内路径（``media/<basename>``）并收集媒体字节。

    ``media_root`` 为源媒体目录（pandoc 抽取的 ``structured/raw/media``）。
    引用优先按原路径匹配，其次按 basename 兜底；找不到的文件对应引用被移除，
    避免 EPUB 出现悬空图片引用。
    """
    media_root = Path(media_root)
    seen: dict[str, bytes] = {}

    def _collect(alt: str, src: str) -> str:
        src = src.strip()
        name = Path(src).name
        epub_path = f"media/{name}"
        if epub_path not in seen:
            data: bytes | None = None
            for cand in (
                media_root / src,
                media_root / name,
                media_root / src.lstrip("/"),
            ):
                try:
                    if cand.is_file():
                        data = cand.read_bytes()
                        break
                except OSError:
                    continue
            if data is not None:
                seen[epub_path] = data
        if epub_path in seen:
            return f"![{alt}]({epub_path})"
        return ""

    def _sub(m: re.Match[str]) -> str:
        return _collect(m.group(1), m.group(2))

    def _html_img(m: re.Match[str]) -> str:
        # HTML <img>（含 <figure>/<a> 包裹）→ 标准 markdown 图片引用
        return _collect("", m.group(1))

    rewritten = _PANDOC_PLACEHOLDER.sub(_placeholder, md_text)
    rewritten = _HTML_FIG_IMG.sub(_html_img, rewritten)
    rewritten = _HTML_IMG.sub(_html_img, rewritten)
    rewritten = _IMG_REF.sub(_sub, rewritten)
    return rewritten, list(seen.items())


def _placeholder(m: re.Match[str]) -> str:
    """pandoc 孤立图片占位 → 标准 markdown 图片引用，交给 _IMG_REF 统一处理。"""
    return f"![{m.group(1)}]({m.group(2).strip()})"


def build_epub(
    pub: Publication,
    entries: list[dict[str, Any]],
    content_files: list[tuple[str, str]],
    *,
    lang: str,
    modified: str,
    out_path: str | Path,
    media_files: list[tuple[str, bytes]] | None = None,
) -> Path:
    """把内容文档 + 媒体资源封装为确定性标准 EPUB 3，返回输出路径。

    ``entries``：构建期单元清单（id/kind/region/title）。
    ``content_files``：``(文件名.xhtml, XHTML 字符串)``，按 spine 顺序。
    ``media_files``：可选 ``(EPUB 内相对 OEBPS/ 路径, 字节)``，如 ``("media/p001.jpg", …)``。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ts = _parse_modified(modified)

    content_entries = _content_entries(entries, content_files)
    spine_ids = [fn for fn, _ in content_files]

    items: list[tuple[str, str, str, str | None]] = [
        ("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        ("ncx", "toc.ncx", "application/x-dtbncx+xml", None),
        ("landmarks", "landmarks.xhtml", "application/xhtml+xml", None),
        ("style", "style.css", "text/css", None),
    ]
    for fn in spine_ids:
        items.append((fn, fn, "application/xhtml+xml", None))
    if media_files:
        for epub_path, _data in media_files:
            ext = Path(epub_path).suffix.lower()
            media_type = _MEDIA_TYPES.get(ext, "application/octet-stream")
            items.append((epub_path, epub_path, media_type, None))

    opf = _render_opf(pub, lang, modified, items, spine_ids)
    nav = _render_nav(pub, entries, content_entries, lang)
    ncx = _render_ncx(pub, entries)
    landmarks = _render_landmarks(entries, lang)
    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        '    <rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    )

    stored = zipfile.ZIP_STORED
    deflated = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(out_path, "w") as zf:
        zf.writestr(_zi("mimetype", ts, stored), "application/epub+zip")
        zf.writestr(_zi("META-INF/container.xml", ts, deflated), container.encode("utf-8"))
        zf.writestr(_zi("OEBPS/content.opf", ts, deflated), opf.encode("utf-8"))
        zf.writestr(_zi("OEBPS/nav.xhtml", ts, deflated), nav.encode("utf-8"))
        zf.writestr(_zi("OEBPS/toc.ncx", ts, deflated), ncx.encode("utf-8"))
        zf.writestr(_zi("OEBPS/landmarks.xhtml", ts, deflated), landmarks.encode("utf-8"))
        zf.writestr(_zi("OEBPS/style.css", ts, deflated), _STYLE_CSS.encode("utf-8"))
        for fn, xhtml in content_files:
            zf.writestr(_zi(f"OEBPS/{fn}", ts, deflated), xhtml.encode("utf-8"))
        if media_files:
            for epub_path, data in media_files:
                zf.writestr(_zi(f"OEBPS/{epub_path}", ts, deflated), data)
    return out_path
