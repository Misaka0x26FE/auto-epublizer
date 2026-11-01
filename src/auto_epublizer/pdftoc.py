# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""印刷目录文字与导航目标的确定性绑定；不按条数或标题子串猜页码。"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlsplit

from lxml import etree

_EPUB = "http://www.idpf.org/2007/ops"
_PAGE = re.compile(r"(?:\s+|[.…·•—–-]+)(?P<page>[0-9]+|[ivxlcdm]+)\s*$", re.I)
_PAGE_ONLY = re.compile(r"^\s*(?P<page>[0-9]+|[ivxlcdm]+)\s*$", re.I)


def member_href(value: str, owner: str = "") -> str | None:
    """包内 URL 只解码一次，允许包内兄弟目录，排除远程和根外身份。"""
    if not value:
        return None
    url = urlsplit(value)
    path = unquote(url.path)
    if url.scheme or url.netloc or path.startswith(("/", "\\")) or "\\" in path:
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(owner), path)) if path else owner
    if target in ("", ".", "..") or target.startswith("../"):
        return None
    return target


def canonical_href(value: str, owner: str = "") -> str | None:
    """路径和 fragment 重新编码后作为身份键，文件名 # 不会混入 fragment。"""
    path = member_href(value, owner)
    if path is None:
        return None
    fragment = unquote(urlsplit(value).fragment)
    return quote(path, safe="/") + ("#" + quote(fragment, safe="") if fragment else "")


def _local(node: etree._Element) -> str:
    return node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""


def _fragment(inner: str) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return etree.fromstring(
        f'<aep xmlns:epub="{_EPUB}" xmlns:xlink="http://www.w3.org/1999/xlink">{inner}</aep>'.encode(),
        parser,
    )


def _label(text: str) -> str:
    return "".join(
        unicodedata.normalize("NFKC", text).strip().rstrip(" .…·•—–-").split()
    ).casefold()


def is_toc_document(inner: str, *, title: str = "", declared: bool = False) -> bool:
    """优先使用明确语义；缺失时只认完整目录标题，不认文件名或子串。"""
    if declared:
        return True
    titles = {
        "目录",
        "目次",
        "目錄",
        "详细目录",
        "contents",
        "tableofcontents",
        "tabledesmatières",
        "inhalt",
        "оглавление",
    }
    if _label(title) in titles:
        return True
    try:
        root = _fragment(inner)
    except etree.XMLSyntaxError:
        return False
    if any(
        "toc" in (node.get(f"{{{_EPUB}}}type") or "").split() or node.get("role") == "doc-toc"
        for node in root.iter()
    ):
        return True
    first_h1 = next((node for node in root.iter() if _local(node) == "h1"), None)
    return first_h1 is not None and _label("".join(first_h1.itertext())) in titles


@dataclass
class TocRewrite:
    html: str
    updates: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)


@dataclass
class AnchorInjection:
    html: str
    markers: dict[str, str] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)


class _AnchorOffsets(HTMLParser):
    def __init__(self, inner: str) -> None:
        super().__init__(convert_charrefs=True)
        self.starts = [0] + [match.end() for match in re.finditer("\n", inner)]
        self.ids: dict[str, list[int]] = defaultdict(list)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        identity = values.get("id") or values.get("xml:id")
        if identity:
            line, column = self.getpos()
            offset = self.starts[line - 1] + column
            if tag not in {"img", "image", "br", "hr", "input", "source", "meta", "link"}:
                offset += len(self.get_starttag_text())
            self.ids[identity].append(offset)


def inject_anchor_markers(
    inner: str,
    entries: list[tuple[int, str, str]],
    *,
    owner_href: str,
    prefix: str = "AEPANCHOR",
) -> AnchorInjection:
    """在真实 id 处插入微型定位标记，保留原标签字节；缺失/重号不猜位置。"""
    result = AnchorInjection(inner)
    parser = _AnchorOffsets(inner)
    parser.feed(inner)
    parser.close()
    insertions = []
    for index, (_, _, href) in enumerate(entries, start=1):
        identity = canonical_href(href)
        fragment = unquote(urlsplit(href).fragment)
        if (
            not identity
            or not fragment
            or member_href(href) != owner_href
            or identity in result.markers
        ):
            continue
        offsets = parser.ids.get(fragment, [])
        if len(offsets) != 1:
            result.findings.append(
                {
                    "level": "error",
                    "code": "E_PDF_ANCHOR_MISSING" if not offsets else "E_PDF_ANCHOR_AMBIGUOUS",
                    "href": identity,
                    "document": owner_href,
                }
            )
            continue
        marker = prefix + f"{index:06d}"
        while marker in inner:
            marker += "X"
        result.markers[identity] = marker
        insertions.append((offsets[0], f'<span class="aepmark aepanchor">{marker}</span>'))
    for offset, markup in sorted(insertions, reverse=True):
        result.html = result.html[:offset] + markup + result.html[offset:]
    return result


@dataclass
class _Token:
    node: etree._Element
    slot: str
    start: int
    end: int
    old: str
    label: str


def _text_slots(node: etree._Element):
    if node.text:
        yield node, "text", node.text
    for child in node:
        yield from _text_slots(child)
        if child.tail:
            yield child, "tail", child.tail


def _token(block: etree._Element) -> _Token | None:
    before = ""
    for node, slot, text in _text_slots(block):
        match = _PAGE.search(text) or _PAGE_ONLY.fullmatch(text)
        if match:
            return _Token(
                node,
                slot,
                match.start("page"),
                match.end("page"),
                match["page"],
                before + text[: match.start("page")],
            )
        before += text
    return None


def rewrite_toc(
    inner: str,
    entries: list[tuple[int, str, str]],
    pages: dict[str, int],
    *,
    owner_href: str,
) -> TocRewrite:
    """只改已绑定目录行中的页码；未定位保留源数字并在成品明确标注来源。"""
    result = TocRewrite(inner)
    try:
        root = _fragment(inner)
    except etree.XMLSyntaxError as exc:
        result.html += (
            '<p class="aep-pdf-unresolved">目录未定位：以下仍为原版页码，非本 PDF 页码。</p>'
        )
        result.findings.append(
            {
                "level": "error",
                "code": "E_PDF_TOC_PARSE",
                "document": owner_href,
                "message": str(exc),
            }
        )
        return result
    by_label: dict[str, set[str]] = defaultdict(set)
    targets: set[str] = set()
    for _, title, href in entries:
        identity = canonical_href(href)
        if identity:
            by_label[_label(title)].add(identity)
            targets.add(identity)
    blocks = [
        node
        for node in root.iter()
        if _local(node) in {"p", "li"}
        and not any(_local(child) in {"p", "li"} for child in node.iterdescendants())
    ]
    pending: list[tuple[etree._Element, _Token | None]] = []

    def candidates(group: list[tuple[etree._Element, _Token | None]]) -> set[str]:
        linked: set[str] = set()
        invalid_title_link = False
        for block, _ in group:
            for node in block.iter():
                if _local(node) != "a" or not node.get("href"):
                    continue
                href = canonical_href(node.get("href"), owner_href)
                if href in targets:
                    linked.add(href)
                elif _label("".join(node.itertext())) in by_label:
                    invalid_title_link = True
        if linked or invalid_title_link:
            return linked
        labels = []
        for index, (block, token) in enumerate(group):
            labels.append(
                token.label if token and index == len(group) - 1 else "".join(block.itertext())
            )
        found = set(by_label.get(_label(" ".join(labels)), set()))
        if len(group) == 1:
            for node in group[0][0].iter():
                if _local(node) == "strong":
                    found.update(by_label.get(_label("".join(node.itertext())), set()))
        return found

    def unresolved(block: etree._Element, token: _Token | None, reason: str) -> None:
        if not any("aep-pdf-unresolved" in (child.get("class") or "").split() for child in block):
            node = etree.SubElement(block, "span", {"class": "aep-pdf-unresolved"})
            node.text = " [原版页码，未定位]"
        result.findings.append(
            {
                "level": "error",
                "code": "E_PDF_TOC_UNLOCATED",
                "document": owner_href,
                "label": token.label.strip() if token else "".join(block.itertext()),
                "old_page": token.old if token else None,
                "reason": reason,
            }
        )

    def apply(group: list[tuple[etree._Element, _Token | None]], href: str) -> None:
        block, token = group[-1]
        page = pages.get(href)
        if type(page) is not int or page < 1:
            unresolved(block, token, "target_unlocated")
            return
        if token:
            text = getattr(token.node, token.slot)
            setattr(token.node, token.slot, text[: token.start] + str(page) + text[token.end :])
        else:
            node = etree.SubElement(block, "span", {"class": "aep-pdf-page"})
            node.text = " " + str(page)
        result.updates.append(
            {
                "href": href,
                "page": page,
                "old_page": token.old if token else None,
                "label": " ".join("".join(node.itertext()) for node, _ in group),
            }
        )

    def flush(group: list[tuple[etree._Element, _Token | None]]) -> None:
        for block, token in group:
            choices = candidates([(block, token)])
            if token:
                unresolved(block, token, "ambiguous_or_unknown_title")
            elif len(choices) == 1:
                apply([(block, token)], next(iter(choices)))

    for block in blocks:
        token = _token(block)
        pending.append((block, token))
        if token is None:
            continue
        matches = []
        for length in range(1, min(4, len(pending)) + 1):
            choices = candidates(pending[-length:])
            if len(choices) == 1:
                matches.append((length, next(iter(choices))))
        if matches and len({href for _, href in matches}) == 1:
            length, href = matches[0]
            flush(pending[:-length])
            apply(pending[-length:], href)
            pending.clear()
    flush(pending)
    if not result.updates and not result.findings:
        result.findings.append(
            {"level": "warning", "code": "W_PDF_TOC_NO_ROWS", "document": owner_href}
        )
    result.html = escape(root.text or "", quote=False) + "".join(
        etree.tostring(node, encoding="unicode") for node in root
    )
    return result
