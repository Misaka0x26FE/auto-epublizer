# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""成品注释门（N5）：独立解析最终 EPUB 的 XHTML，与已登记注释逐条对账。

**独立性**：本模块不使用构建渲染函数重建期望，也不读构建中间态——只读成品 XML、
源媒体路径和已登记数据（``structured/notes.json`` / ``translation/notes.json``），逐项核验：

- 每个已登记 ``ref_id`` 在成品中**恰好一个** noteref 锚点，且 href 指向真实存在的
  ``<file>#fn-<note_id>``；
- 每条被引注文**恰好一个** ``epub:type="footnote"`` aside，含完整注文（内容核对）；
- aside 回链覆盖**每条引用**且目标锚点可解析（一注多引/跨文件）；
- 成品里出现未登记的 noteref/aside → 报告（孤儿）；
- ``inventory=none``（经核证无注）时零 noteref / 零 aside 合法（零对零）。

门禁为 error 级：任一 finding 阻断放行（由 ``qa/report.py`` 聚合）。
"""

from __future__ import annotations

import html as html_lib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from auto_common.markdown import (
    CODE_SPAN_RE,
    fence_body,
    inline_code_chunks,
    markdown_chunks,
    paragraph_blocks,
)

from ..media_paths import epub_member_path, resolve_media_path

_TAG_RE = re.compile(r"<[^>]+>")
_ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
_ASIDE_RE = re.compile(
    r'<aside\b([^>]*epub:type="footnote"[^>]*)>(.*?)</aside>', re.DOTALL | re.IGNORECASE
)
_ATTR_RE = re.compile(r"""([\w:.-]+)\s*=\s*(["'])(.*?)\2""", re.DOTALL)


def _attrs(tag: str) -> dict[str, str]:
    return {m.group(1): m.group(3) for m in _ATTR_RE.finditer(tag)}


def _unescape(text: str) -> str:
    """HTML 实体反转义（单遍，与浏览器解码一致）。

    渲染器把撇号等标点转成**数字实体**（``&#x27;``），只解具名实体会让注文正文
    比对必然失配（误报 E_NOTES_CONTENT_MISMATCH）。``html.unescape`` 单遍解具名与
    数字实体，语义与阅读器一致。
    """
    return html_lib.unescape(text)


def _norm_html(html: str) -> str:
    return re.sub(r"\s+", "", _unescape(_TAG_RE.sub("", html)))


def _norm_md(md: str) -> str:
    """注文 Markdown → 比对用规范形（与构建器同口径：去标记符号与空白）。

    与构建器 `build/html.py::_inline` 的规则一一对应：行内代码跨度原样保留
    （内容不被其它规则处理）、粗体/斜体只脱**配对**标记（裸下划线与裸反引号
    是字面量，不能连坐）、反斜杠转义脱去、链接留标签、锚点与属性块不留文字。
    """
    out: list[str] = []
    for block in paragraph_blocks(md or ""):
        kind, chunk = markdown_chunks(block)[0]
        if kind == "code":
            out.append(fence_body(chunk))
            continue
        if kind == "raw":
            out.append(_norm_html(fence_body(chunk)))
            continue
        text = _note_block_prose(chunk)
        for code, part in inline_code_chunks(text):
            if code:
                match = CODE_SPAN_RE.fullmatch(part)
                out.append(match[2] if match else part)
            else:
                out.append(_norm_md_text(part))
    return re.sub(r"\s+", "", "".join(out))


def _note_block_prose(block: str) -> str:
    """独立读取 Markdown 块的可见文字；不吞掉非连续原印列表号。"""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if (
        lines
        and all(re.match(r"^(?:>|\|)\s", line) for line in lines)
        and len({line[0] for line in lines}) == 1
    ):
        return "\n".join(line[1:].lstrip() for line in lines)
    if lines and all(re.match(r"^[-*+]\s+", line) for line in lines):
        return "\n".join(re.sub(r"^[-*+]\s+", "", line) for line in lines)
    ordered = [re.match(r"^(\d+)([.)、])\s+(.*)$", line) for line in lines]
    if ordered and all(ordered):
        numbers = [int(m[1]) for m in ordered if m]
        if numbers == list(range(1, len(lines) + 1)) and all(
            m[2] in (".", "、") for m in ordered if m
        ):
            return "\n".join(m[3] for m in ordered if m)
    return block


def _norm_md_text(text: str) -> str:
    """非代码部分的 Markdown → 规范形（标记符号脱除）。"""
    # 独立 Markdown 图片会渲染可见 figcaption，内嵌图片则仅有 alt；两者不能一概删字。
    text = "\n".join(
        line.strip()[2 : line.strip().index("]")] if _MD_IMG_RE.fullmatch(line.strip()) else line
        for line in text.splitlines()
    )
    text = _MD_HEADING_ID_RE.sub(r"\1", text)  # 标题行尾 id 属性（渲染后不印出）
    text = _MD_ANCHOR_INLINE_RE.sub("", text)  # 内联锚点（渲染为 <a id>，无文字）
    text = _MD_EMPTY_ATTR_RE.sub("", text)  # 空属性块 {[]}（渲染时丢弃）
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)  # 标题标记
    text = _MD_BOLD_RE.sub(r"\1", text)  # 粗体标记（配对才脱）
    text = _MD_ITALIC_RE.sub(r"\1", text)  # 斜体标记（配对才脱）
    text = _MD_IMG_RE.sub("", text)  # 图片留空（包含源文件名中的括号）
    text = _IMG_RE.sub("", text)  # HTML 图片同样留空（媒体由专用核对负责）
    text = re.sub(r"</?svg\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接留标签
    # CommonMark 自动链接 `<http://…>` / `<user@example.com>`：渲染成 <a> 后只剩
    # 标签文字，尖括号不印出；比对侧须同样去掉尖括号，否则含 URL 的注文必然误报。
    text = _MD_AUTOLINK_RE.sub(r"\1", text)
    # pandoc 反斜杠转义（`\[` `\]` `\.` …）：渲染器在最后一步脱去反斜杠，
    # 比对侧必须同口径（否则含转义的注文必然误报「内容不符」）。
    text = _MD_ESCAPED_PUNCT_RE.sub(r"\1", text)
    return text


def _norm_href(href: str) -> str:
    """EPUB 内相对 href 规范化（去掉可选的 OEBPS/ 前缀，便于比较）。"""
    h = (href or "").strip()
    return h[len("OEBPS/") :] if h.startswith("OEBPS/") else h


_IMG_RE = re.compile(r"<(?:img|image)\b[^>]*>", re.IGNORECASE)
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)")

# 渲染期被**消费掉**的 Markdown 语法（成品里不印出，比对时须从登记文本中剥离）：
# 内联锚点 `[]{#id}` → <a id>；空属性块 `{[]}` → 丢弃；标题行尾 id `## 标题 {#id}` → 标题 id。
_MD_ANCHOR_INLINE_RE = re.compile(r"\[\][ \t]*\{#?[\w:.-]+\}")
_MD_EMPTY_ATTR_RE = re.compile(r"\{[ \t]*\[[ \t]*\][ \t]*\}")
_MD_HEADING_ID_RE = re.compile(r"(?m)^(#{1,6}[^\n]*?)\s*\{#[\w:.-]+\}\s*$")
# 与构建器 `build/html.py::_ESCAPED_PUNCT_RE` 同集：pandoc 反斜杠转义
_MD_ESCAPED_PUNCT_RE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")
# 粗体/斜体：只脱**配对**标记（裸 `_` 与裸反引号是字面量，不能连坐删除）
_MD_BOLD_RE = re.compile(r"\*\*((?:[^*]|\\\*)+)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
# CommonMark 自动链接：绝对 URI（带 scheme）或邮箱；渲染后尖括号不保留。
_MD_AUTOLINK_RE = re.compile(
    r"<((?:[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^<>\s]*)"
    r"|(?:[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+))>"
)
_PLACEHOLDER_IMG_RE = re.compile(r'original-image-src="([^"]+)"')


def _source_media_refs(md: str, media_root: Path) -> tuple[set[str], set[str]]:
    """按真实源文件定位期望成员；源路径百分号不解码，HTML URL 只解码一次。"""
    # 只复用语法上下文，不通过注文渲染器构造期望内容。
    from auto_common.markdown import inline_code_chunks, markdown_chunks

    md = "".join(
        chunk
        if kind == "raw"
        else "".join(part for is_code, part in inline_code_chunks(chunk) if not is_code)
        for kind, chunk in markdown_chunks(md or "")
        if kind != "code"
    )
    refs = [m.group(1) for m in _MD_IMG_RE.finditer(md or "")]
    refs.extend(m.group(1) for m in _PLACEHOLDER_IMG_RE.finditer(md or ""))
    missing: set[str] = set()
    for image in _IMG_RE.finditer(md or ""):
        attrs = _attrs(image.group(0))
        src = attrs.get("src") or attrs.get("href") or attrs.get("xlink:href") or ""
        if not src:
            continue
        url = urlsplit(html_lib.unescape(src))
        if url.scheme or url.netloc:
            missing.add(src)
        else:
            refs.append(unquote(url.path))
    members: set[str] = set()
    for ref in refs:
        resolved = resolve_media_path(ref, media_root)
        if resolved is None:
            missing.add(ref)
        else:
            members.add(f"OEBPS/media/{resolved.relative_to(media_root).as_posix()}")
    return members, missing


def _aside_media_refs(html: str, document: str) -> set[str]:
    """将 HTML 图片 URL 解码一次并按文档目录解析为字面 ZIP 成员名。"""
    members: set[str] = set()
    for image in _IMG_RE.finditer(html or ""):
        attrs = _attrs(image.group(0))
        src = attrs.get("src") or attrs.get("href") or attrs.get("xlink:href") or ""
        if not src:
            continue
        members.add(epub_member_path(document, src) or src)
    return members


def epub_render_mode(epub_path: str | Path) -> str | None:
    """经 container 定位 OPF，读取唯一合法的实际打包模式。"""
    try:
        with zipfile.ZipFile(epub_path) as archive:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(
                "{urn:oasis:names:tc:opendocument:xmlns:container}rootfiles/"
                "{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            )
            if rootfile is None:
                return None
            opf_path = rootfile.get("full-path")
            if not opf_path:
                return None
            package = ElementTree.fromstring(archive.read(opf_path))
        modes = [
            (meta.text or "").strip()
            for meta in package.findall(
                "{http://www.idpf.org/2007/opf}metadata/{http://www.idpf.org/2007/opf}meta"
            )
            if meta.get("property") == "aep:render-mode"
        ]
        if len(modes) != 1 or modes[0] not in {"source", "translation"}:
            return None
        return modes[0]
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
        return None


@dataclass
class NotesAuditResult:
    missing: list[str] = field(default_factory=list)  # 登记了但成品缺/错/不匹配
    orphan: list[str] = field(default_factory=list)  # 成品有但未登记
    findings: list[dict[str, Any]] = field(default_factory=list)

    def add(self, code: str, message: str, *, missing: str | None = None) -> None:
        self.findings.append({"level": "error", "code": code, "message": message})
        if missing is not None:
            self.missing.append(missing)

    @property
    def ok(self) -> bool:
        return not self.findings


def audit_notes_epub(
    epub_path: str | Path,
    *,
    source_notes: dict[str, Any],
    target_notes: dict[str, Any] | None,
    media_root: Path,
) -> NotesAuditResult:
    """成品注释门（N5）。返回 result；``ok=False`` 表示必须阻断放行。"""
    result = NotesAuditResult()
    media_root = media_root.resolve()
    inventory = str(source_notes.get("inventory") or "")
    refs = [r for r in (source_notes.get("references") or []) if isinstance(r, dict)]
    note_by_id = {
        str(n.get("note_id")): n
        for n in (source_notes.get("notes") or [])
        if isinstance(n, dict) and n.get("note_id")
    }
    target_by_id = {
        str(t.get("note_id")): t
        for t in ((target_notes or {}).get("notes") or [])
        if isinstance(t, dict) and t.get("note_id")
    }
    path = Path(epub_path)
    if not path.is_file():
        result.add("E_NOTES_EPUB", f"成品不存在：{path}", missing=str(path))
        return result
    with zipfile.ZipFile(path) as zf:
        all_names = set(zf.namelist())
        files = [n for n in all_names if n.startswith("OEBPS/") and n.endswith(".xhtml")]
        content = {n: zf.read(n).decode("utf-8", errors="replace") for n in files}
    # 收集成品中的 noteref 锚点与 footnote aside（含 id → 位置）
    anchor_by_id: dict[str, tuple[str, str]] = {}
    aside_by_id: dict[str, tuple[int, str, str]] = {}
    for name, html in content.items():
        for m in _ANCHOR_RE.finditer(html):
            a = _attrs(m.group(0))
            if a.get("epub:type") == "noteref" and a.get("id"):
                rid = a["id"]
                if rid in anchor_by_id:
                    result.add("E_NOTES_DUP_ANCHOR", f"noteref 锚点重复：{rid}", missing=rid)
                anchor_by_id[rid] = (name, a.get("href", ""))
        for m in _ASIDE_RE.finditer(html):
            a = _attrs(m.group(1))
            nid = a.get("id") or ""
            if nid.startswith("fn-"):
                nid = nid[3:]  # 约定：aside id = fn-<note_id>（构建与审计共用同一身份）
            if not nid:
                continue
            if nid in aside_by_id:
                result.add("E_NOTES_DUP_ASIDE", f"注文 aside 重复：{nid}", missing=nid)
            aside_by_id[nid] = (m.start(), m.group(2), name)

    if inventory == "none":
        if anchor_by_id or aside_by_id:
            result.add(
                "E_NOTES_NONE_UNEXPECTED",
                f"已核证无注（inventory=none），成品却有 noteref {len(anchor_by_id)} 个 / "
                f"aside {len(aside_by_id)} 个",
                missing="inventory=none",
            )
        return result

    registered_ids = {str(r.get("ref_id")) for r in refs}
    referenced_notes = {str(r.get("note_id")) for r in refs}
    kept_notes = {
        nid for nid, n in note_by_id.items() if nid not in referenced_notes and n.get("orphan_ok")
    }
    # 反向：成品有而未登记
    for rid in sorted(set(anchor_by_id) - registered_ids):
        result.orphan.append(rid)
        result.add("E_NOTES_ORPHAN_ANCHOR", f"成品出现未登记的 noteref 锚点：{rid}")
    for nid in sorted(set(aside_by_id) - referenced_notes - kept_notes):
        result.orphan.append(nid)
        result.add("E_NOTES_ORPHAN_ASIDE", f"成品出现未登记的注文 aside：{nid}")

    for r in refs:
        rid = str(r.get("ref_id"))
        nid = str(r.get("note_id"))
        note = note_by_id.get(nid)
        if note is None:
            result.add("E_NOTES_REF_NO_NOTE", f"引用 {rid} 指向未登记注文：{nid}", missing=rid)
            continue
        anchor = anchor_by_id.get(rid)
        if anchor is None:
            result.add("E_NOTES_ANCHOR_MISSING", f"成品缺引用锚点：{rid}", missing=rid)
            continue
        file_name, href = anchor
        target = href.split("#", 1)[0]
        frag = href.split("#", 1)[1] if "#" in href else ""
        if frag != f"fn-{nid}":
            result.add(
                "E_NOTES_HREF_WRONG",
                f"引用 {rid} 的 href 目标错：{href}（应指向 fn-{nid}）",
                missing=rid,
            )
            continue
        target_key = f"OEBPS/{target}" if target and not target.startswith("OEBPS/") else target
        if target and target_key not in content:
            result.add(
                "E_NOTES_HREF_FILE", f"引用 {rid} 的 href 指向不存在的文件：{href}", missing=rid
            )
            continue
        # 回链必须覆盖这次引用
        aside = aside_by_id.get(nid)
        if aside is None or (target and aside[2] != target_key):
            result.add(
                "E_NOTES_ASIDE_MISSING",
                f"引用 {rid} 指向的注文缺少 aside：fn-{nid}",
                missing=rid,
            )
            continue
        aside_inner = aside[1]
        back_hrefs = []
        for m in _ANCHOR_RE.finditer(aside_inner):
            a = _attrs(m.group(0))
            if a.get("epub:type") == "backlink" and a.get("href"):
                back_hrefs.append(a["href"])
        # 回链必须**完整指向该引用**（文件 + fragment），不能只看 fragment：
        # 跨文件复引时回链指错文件同样会让读者跳错位置。
        anchor_file_name = Path(anchor[0]).name
        want_back = _norm_href(f"{anchor_file_name}#{rid}")
        if want_back not in {_norm_href(h) for h in back_hrefs}:
            result.add(
                "E_NOTES_BACKLINK_MISSING",
                f"注文 fn-{nid} 缺到引用 {rid} 的回链（应指向 {want_back}）",
                missing=rid,
            )

    # 一注多引：aside 文本核对（译文优先；源文回退用源文本）
    for nid in sorted(referenced_notes | kept_notes):
        aside = aside_by_id.get(nid)
        if aside is None:
            result.add("E_NOTES_ASIDE_MISSING", f"注文 {nid} 在成品中没有 aside", missing=nid)
            continue
        expected = ""
        expected_md = ""
        t = target_by_id.get(nid)
        if t is not None and str(t.get("target_markdown") or "").strip():
            expected_md = str(t["target_markdown"])
        else:
            expected_md = str((note_by_id.get(nid) or {}).get("source_markdown") or "")
        expected = _norm_md(expected_md)
        # 仅移除渲染器添加的首个显示号和语义回链；不能用子串包含放过附加正文。
        body = re.sub(r"^\s*<p>\[\d+\]</p>", "", aside[1], count=1)
        body = re.sub(
            r"<a\b[^>]*>.*?</a>",
            lambda m: "" if _attrs(m.group(0)).get("epub:type") == "backlink" else m.group(0),
            body,
            flags=re.DOTALL | re.IGNORECASE,
        )
        actual = _norm_html(body)
        if actual != expected:
            result.add(
                "E_NOTES_CONTENT_MISMATCH",
                f"注文 {nid} 的成品内容与登记文本不符（疑错配/截断）",
                missing=nid,
            )
        # P1 漏门修复：`_norm_md` 会把图片引用整段去掉，缺图不能被文本对账掩盖——
        # 注文媒体必须单独核对（期待引用 ⊆ aside 实渲染），且实渲染资源必须在包内。
        want_media, missing_sources = _source_media_refs(expected_md, media_root)
        have_media = _aside_media_refs(aside[1], aside[2])
        if missing_sources:
            result.add(
                "E_NOTES_MEDIA_MISSING",
                f"注文 {nid} 的源图片不存在或越界：{'、'.join(sorted(missing_sources)[:4])}",
                missing=nid,
            )
        if want_media and not want_media <= have_media:
            # F4：完整资源身份；同名不同目录不得互相冒充
            result.add(
                "E_NOTES_MEDIA_MISSING",
                f"注文 {nid} 的图片未渲染进 aside：{'、'.join(sorted(want_media - have_media)[:4])}",
                missing=nid,
            )
        for ref in sorted(have_media):
            if ref not in all_names:
                result.add(
                    "E_NOTES_MEDIA_ABSENT",
                    f"注文 {nid} 的图片资源不在包内：{ref}",
                    missing=nid,
                )
    return result
