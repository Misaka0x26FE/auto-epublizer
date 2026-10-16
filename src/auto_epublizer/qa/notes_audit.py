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

import re
import zipfile
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from ..media_paths import epub_member_path, resolve_media_path

_TAG_RE = re.compile(r"<[^>]+>")
_ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)
_ASIDE_RE = re.compile(
    r'<aside\b([^>]*epub:type="footnote"[^>]*)>(.*?)</aside>', re.DOTALL | re.IGNORECASE
)
_ATTR_RE = re.compile(r'([\w:.-]+)="([^"]*)"')


def _attrs(tag: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _ATTR_RE.finditer(tag)}


def _unescape(text: str) -> str:
    for src, dst in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(src, dst)
    return text.replace("&#39;", "'").replace("&apos;", "'")


def _norm_html(html: str) -> str:
    return re.sub(r"\s+", "", _unescape(_TAG_RE.sub("", html)))


def _norm_md(md: str) -> str:
    """注文 Markdown → 比对用规范形（去标记符号与空白；用于发现空/错内容）。"""
    text = md or ""
    text = re.sub(r"(?m)^\s{0,3}(?:[-*+]|\d+[.)])\s+", "", text)  # 列表标记
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)  # 标题标记
    text = re.sub(r"[*_`]+", "", text)
    text = _MD_IMG_RE.sub("", text)  # 图片留空（包含源文件名中的括号）
    text = _IMG_RE.sub("", text)  # HTML 图片同样留空（媒体由专用核对负责）
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接留标签
    return re.sub(r"\s+", "", text)


def _norm_href(href: str) -> str:
    """EPUB 内相对 href 规范化（去掉可选的 OEBPS/ 前缀，便于比较）。"""
    h = (href or "").strip()
    return h[len("OEBPS/") :] if h.startswith("OEBPS/") else h


_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
_PLACEHOLDER_IMG_RE = re.compile(r'original-image-src="([^"]+)"')


def _source_media_refs(md: str, media_root: Path) -> tuple[set[str], set[str]]:
    """按真实源文件定位期望成员；源路径百分号不解码，HTML URL 只解码一次。"""
    refs = [m.group(1) for m in _MD_IMG_RE.finditer(md or "")]
    refs.extend(m.group(1) for m in _PLACEHOLDER_IMG_RE.finditer(md or ""))
    missing: set[str] = set()
    for image in _IMG_RE.finditer(md or ""):
        src = _attrs(image.group(0)).get("src") or ""
        if not src:
            continue
        url = urlsplit(unescape(src))
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
        src = _attrs(image.group(0)).get("src") or ""
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
        actual = _norm_html(aside[1])
        if expected and expected not in actual:
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
