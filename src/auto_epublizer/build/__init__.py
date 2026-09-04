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
from urllib.parse import quote

from auto_common.workspace import Publication

from .html import slug_file

_IMG_REF = re.compile(r"!\[([^\]]*)\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
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

# 内置基础样式：仅功能性规则（epub-template-spec §4 呈现层）——
# 字体/颜色/字号/行距/正文缩进/对齐一律不设，交由阅读器决定；
# 有限个性化由主题层（P1 预置主题）提供。图片「只缩不放大居中」是功能性规则必须保留。
_STYLE_CSS = """\
img {
  max-width: 100%;
  height: auto;
}
p.imgp {
  text-indent: 0;
  text-align: center; /* 图片段居中、不缩进 */
}
section.footnotes {
  margin-top: 2em;
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


def _toc_depths(entries: list[dict[str, Any]]) -> list[int]:
    """把单元标题层级（entry['level']，缺省 1）归一化为目录嵌套深度。

    规则：首个单元为深度 1；层级递增 → 子级（跳级封顶为父级+1）；层级回落 → 回到
    最近祖先的下一级。全平级时全部深度为 1（扁平目录）。
    """
    depths: list[int] = []
    stack: list[int] = []
    for e in entries:
        lv = int(e.get("level") or 1)
        while stack and stack[-1] >= lv:
            stack.pop()
        depths.append(len(stack) + 1)
        stack.append(lv)
    return depths


def toc_depths(entries: list[dict[str, Any]]) -> list[int]:
    """公开别名：单元清单 → 目录嵌套深度（qa/provenance 与 build 共用同一算法）。"""
    return _toc_depths(entries)


def _toc_tree(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按嵌套深度把单元清单组织成目录树：[{entry, children: […]}]。"""
    tree: list[dict[str, Any]] = []
    stack: list[tuple[int, list[dict[str, Any]]]] = [(0, tree)]
    for e, d in zip(entries, _toc_depths(entries), strict=False):
        node: dict[str, Any] = {"entry": e, "children": []}
        while stack and stack[-1][0] >= d:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((d, node["children"]))
    return tree


def _render_nav_items(nodes: list[dict[str, Any]]) -> str:
    """递归渲染 nav 嵌套 <li>（含子级 <ol>）。"""
    lis: list[str] = []
    for node in nodes:
        e = node["entry"]
        href = f"{slug_file(e['id'])}.xhtml"
        label = escape(e["title"] or e["id"])
        if node["children"]:
            lis.append(
                f'      <li><a href="{href}">{label}</a>\n'
                f"        <ol>\n{_render_nav_items(node['children'])}\n        </ol>\n"
                f"      </li>"
            )
        else:
            lis.append(f'      <li><a href="{href}">{label}</a></li>')
    return "\n".join(lis)


def _render_nav(
    pub: Publication,
    entries: list[dict[str, Any]],
    content_entries: list[dict[str, Any]],
    lang: str,
) -> str:
    """渲染 EPUB 3 导航文档（nav.xhtml，epub:type=toc），层级按源文标题层级嵌套。"""
    items = _render_nav_items(_toc_tree(content_entries))
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
        f"{items}\n"
        "  </ol>\n"
        "</nav>\n"
        "</body>\n"
        "</html>\n"
    )


def _render_ncx_points(nodes: list[dict[str, Any]], counter: list[int]) -> str:
    """递归渲染 NCX 嵌套 <navPoint>（playOrder 按先序遍历连续编号）。"""
    out: list[str] = []
    for node in nodes:
        counter[0] += 1
        n = counter[0]
        e = node["entry"]
        href = f"{slug_file(e['id'])}.xhtml"
        label = e["title"] or e["id"]
        head = (
            f'    <navPoint id="navpoint-{n}" playOrder="{n}">\n'
            f"      <navLabel><text>{escape(label)}</text></navLabel>\n"
            f'      <content src="{escape(href)}"/>'
        )
        if node["children"]:
            out.append(f"{head}\n{_render_ncx_points(node['children'], counter)}\n    </navPoint>")
        else:
            out.append(f"{head}\n    </navPoint>")
    return "\n".join(out)


def _render_ncx(
    pub: Publication,
    content_entries: list[dict[str, Any]],
) -> str:
    """渲染 NCX（toc.ncx，向后兼容）；层级嵌套，只引用实际生成的内容文档防悬空。"""
    uid = pub.slug
    depths = _toc_depths(content_entries)
    depth = max(depths) if depths else 1
    body = _render_ncx_points(_toc_tree(content_entries), [0]) or "    <!-- 无目录条目 -->"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        "  <head>\n"
        f'    <meta name="dtb:uid" content="{escape(uid)}"/>\n'
        f'    <meta name="dtb:depth" content="{depth}"/>\n'
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
    content_entries: list[dict[str, Any]],
    lang: str,
) -> str:
    """渲染 landmarks（frontmatter / bodymatter / backmatter 地标）。

    只引用实际生成的内容文档（防悬空）；每类 region 取首个可用条目。
    """
    landmarks: list[tuple[str, str, str]] = []
    labels = {
        "frontmatter": "前言",
        "bodymatter": "正文",
        "backmatter": "附录",
    }
    for region in ("frontmatter", "bodymatter", "backmatter"):
        for e in content_entries:
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
    """改写 md 中图片引用为 EPUB 内路径（``media/…``）并收集媒体字节。

    ``media_root`` 为源媒体目录（pandoc 抽取的 ``structured/raw/media``）。
    引用优先按原相对路径解析（保留子目录，避免同名不同目录错配），
    其次按 basename 兜底；找不到的文件对应引用被移除，避免悬空图片引用。
    文件名含括号等特殊字符时 URL 引用按需百分号编码。
    """
    media_root = Path(media_root).resolve()
    seen: dict[str, bytes] = {}

    def _resolve(rel: str) -> tuple[str, bytes] | None:
        """按候选顺序解析媒体文件，返回 (media_root 相对路径, 字节)。

        候选：原相对路径 → 去掉与 media_root 尾部重复的前缀（raw/media/x.png
        当 media_root 为 …/raw/media 时 → x.png）→ basename 兜底。
        """
        candidates = [rel]
        parts = Path(rel).parts
        root_parts = media_root.parts
        # 去掉与 media_root 尾部重复的前缀段
        for k in range(1, len(parts)):
            if list(parts[:k]) == list(root_parts[-k:]):
                candidates.append(str(Path(*parts[k:])))
                break
        candidates.append(Path(rel).name)
        for cand in candidates:
            p = media_root / cand
            try:
                if p.is_file():
                    return p.relative_to(media_root).as_posix(), p.read_bytes()
            except OSError:
                continue
        return None

    def _collect(alt: str, src: str) -> str:
        rel = src.strip().lstrip("/")
        resolved = _resolve(rel)
        if resolved is None:
            return ""
        inner, data = resolved
        epub_path = f"media/{inner}"
        seen.setdefault(epub_path, data)
        href = quote(inner)
        return f"![{alt}](media/{href})"

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
            # href 与 XHTML 内引用一致（URL 编码特殊字符）
            href = quote(epub_path)
            items.append((epub_path, href, media_type, None))

    opf = _render_opf(pub, lang, modified, items, spine_ids)
    nav = _render_nav(pub, entries, content_entries, lang)
    ncx = _render_ncx(pub, content_entries)
    landmarks = _render_landmarks(content_entries, lang)
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
