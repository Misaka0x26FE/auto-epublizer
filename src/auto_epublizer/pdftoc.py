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


def _own_text_slots(node: etree._Element):
    """块自身的文字槽：跳过嵌套 ``ol``/``ul`` 子树（父条目不吞子条目）。"""
    if node.text:
        yield node, "text", node.text
    for child in node:
        if _local(child) in {"ol", "ul", "li"}:
            if child.tail:
                yield child, "tail", child.tail
            continue
        yield from _own_text_slots(child)
        if child.tail:
            yield child, "tail", child.tail


def _own_only(block: etree._Element) -> bool:
    return any(_local(child) in {"ol", "ul"} for child in block.iterdescendants())


def _own_nodes(block: etree._Element, *, _root: bool = True):
    """块自身作用域的节点：任意深度的嵌套列表条目不参与父条目绑定。"""
    if not _root and _local(block) in {"ol", "ul", "li"}:
        return
    if not _own_only(block):
        yield from block.iter()
        return
    yield block
    for child in block:
        yield from _own_nodes(child, _root=False)


def _block_text(block: etree._Element) -> str:
    if not _own_only(block):
        return "".join(block.itertext())
    return "".join(text for _, _, text in _own_text_slots(block))


def _token(block: etree._Element) -> _Token | None:
    before = ""
    slots = _own_text_slots(block) if _own_only(block) else _text_slots(block)
    for node, slot, text in slots:
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
    document_titles: dict[str, str] | None = None,
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
    nav_label_by_href: dict[str, str] = {}
    for _, title, href in entries:
        identity = canonical_href(href)
        if identity:
            by_label[_label(title)].add(identity)
            targets.add(identity)
            nav_label_by_href.setdefault(identity, title)

    def _classes(node: etree._Element) -> set[str]:
        return set((node.get("class") or "").split())

    blocks: list[etree._Element] = []
    for node in root.iter():
        local = _local(node)
        if local == "div" and "toc-row" in _classes(node):
            # 生成目录的单元格：父 li 含子 ol，不能整行当块；行容器才是页码槽。
            blocks.append(node)
            continue
        if local not in {"p", "li"}:
            continue
        nested_rows = any(
            _local(child) == "div" and "toc-row" in _classes(child)
            for child in node.iterdescendants()
        )
        nested_blocks = any(_local(child) in {"p", "li"} for child in node.iterdescendants())
        if local == "li" and nested_blocks and not nested_rows:
            # 纯 HTML 目录：父 li 自带页码并含子 ol；行容器不存在，父条目仍是块，
            # 但只取自身文字，不吞子条目标签。
            if not _block_text(node).strip():
                continue
            blocks.append(node)
            continue
        if nested_blocks or nested_rows:
            continue
        blocks.append(node)
    pending: list[tuple[etree._Element, _Token | None]] = []

    def candidates(group: list[tuple[etree._Element, _Token | None]]) -> set[str]:
        linked: set[str] = set()
        invalid_title_link = False
        for block, _ in group:
            for node in _own_nodes(block):
                if _local(node) != "a" or not node.get("href"):
                    continue
                raw_href = node.get("href") or ""
                href = canonical_href(raw_href, owner_href)
                if href not in targets:
                    # 生成目录的 href 来自单元/包根，不总是相对目录文件；按 owner
                    # 的各级祖先目录（含包根）依次解析。只有锚文本与 nav 条目标题
                    # 一致才接受回退，避免把张冠李戴的相对路径绑到别的章。
                    anchor_label = _label("".join(node.itertext()))
                    parts = owner_href.split("/")[:-1]
                    for depth in range(len(parts) - 1, -1, -1):
                        base = "/".join(parts[:depth] + ["_aep_base.xhtml"])
                        for candidate in (
                            canonical_href(raw_href, base),
                            canonical_href(raw_href) if depth == 0 else None,
                        ):
                            if not candidate or candidate not in targets:
                                continue
                            nav_label = nav_label_by_href.get(candidate)
                            if nav_label and anchor_label != _label(nav_label):
                                continue
                            href = candidate
                            break
                        if href in targets:
                            break
                if href in targets:
                    linked.add(href)
                elif _label("".join(node.itertext())) in by_label:
                    invalid_title_link = True
        if linked or invalid_title_link:
            return linked
        labels = []
        for index, (block, token) in enumerate(group):
            labels.append(token.label if token and index == len(group) - 1 else _block_text(block))
        found = set(by_label.get(_label(" ".join(labels)), set()))
        if len(group) == 1:
            for node in _own_nodes(group[0][0]):
                if _local(node) == "strong":
                    found.update(by_label.get(_label("".join(node.itertext())), set()))
        return found

    def _append_marker(block: etree._Element, cls: str, text: str) -> None:
        """页码/未定位标记放在父标签容器内，不能落到子列表之后。"""
        node = etree.Element("span", {"class": cls})
        node.text = text
        first_list = next(
            (index for index, child in enumerate(block) if _local(child) in {"ol", "ul"}),
            None,
        )
        if first_list is None:
            block.append(node)
        else:
            block.insert(first_list, node)

    def unresolved(block: etree._Element, token: _Token | None, reason: str) -> None:
        if not any("aep-pdf-unresolved" in (child.get("class") or "").split() for child in block):
            _append_marker(block, "aep-pdf-unresolved", " [原版页码，未定位]")
        result.findings.append(
            {
                "level": "error",
                "code": "E_PDF_TOC_UNLOCATED",
                "document": owner_href,
                "label": token.label.strip() if token else _block_text(block),
                "old_page": token.old if token else None,
                "reason": reason,
            }
        )

    def apply(group: list[tuple[etree._Element, _Token | None]], href: str) -> None:
        block, token = group[-1]
        label_text = token.label if token else _block_text(block)
        # 无 fragment 的 nav 条目若是「§ 级」标题，按章首页回填就是静默错误；
        # 只有标题与目标文档 h1 相同才允许用章起始页，否则显式未定位。
        if not urlsplit(href).fragment and document_titles:
            doc_title = document_titles.get(href)
            nav_title = nav_label_by_href.get(href)
            # 行标签等于 nav 自己的标题或目标文档 h1，就是章级条目，取章起始页；
            # 两者都不等才是 § 级条目，不能静默取章首页。
            section_like = bool(
                nav_title
                and re.match(
                    r"^\s*(?:§|第\s*[0-9一二三四五六七八九十百]+\s*节|section\b)",
                    nav_title,
                    re.I,
                )
            )
            if section_like:
                unresolved(block, token, "no_fragment_for_subheading")
                return
            if (
                doc_title
                and (not nav_title or _label(label_text) != _label(nav_title))
                and _label(label_text) != _label(doc_title)
            ):
                # 既不是 nav 的章级标题也不是目标 h1：可能是无 fragment 的 §，
                # 但无法仅凭文本判定；保留章起始页并记 warning，交人工核对。
                result.findings.append(
                    {
                        "level": "warning",
                        "code": "W_PDF_TOC_SECTION_UNLOCATED",
                        "document": owner_href,
                        "label": label_text.strip(),
                    }
                )
        page = pages.get(href)
        if type(page) is not int or page < 1:
            unresolved(block, token, "target_unlocated")
            return
        # label 必须在改写页码之前取：否则短标题会变成 “Alpha5”，后续对账自证成立。
        label = " ".join(
            [
                *(("".join(node.itertext()) for node, _ in group[:-1])),
                token.label if token else _block_text(block),
            ]
        ).strip()
        if token:
            text = getattr(token.node, token.slot)
            setattr(token.node, token.slot, text[: token.start] + str(page) + text[token.end :])
        else:
            _append_marker(block, "aep-pdf-page", " " + str(page))
        result.updates.append(
            {
                "href": href,
                "page": page,
                "old_page": token.old if token else None,
                "label": label,
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
    # 输出会作为 HTML 解析（Chromium）：不能用 XML 自闭合写法，否则 `<span/>`
    # 会吞掉后续节点（目录行点线/页码布局失效）。
    result.html = escape(root.text or "", quote=False) + "".join(
        etree.tostring(node, encoding="unicode", method="html") for node in root
    )
    return result
