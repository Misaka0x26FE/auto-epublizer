"""把结构化 Markdown 单元转成 XHTML 内容文档。"""

from __future__ import annotations

import html
import re
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _escape_text(text: str) -> str:
    return html.escape(text, quote=False)


def markdown_to_xhtml(md_text: str) -> str:
    """把 Markdown（标题 + 段落）渲染为 XHTML body 片段。"""
    out: list[str] = []
    for raw in md_text.splitlines():
        stripped = raw.rstrip()
        m = _HEADING.match(stripped)
        if m:
            level = min(6, len(m.group(1)))
            out.append(f"<h{level}>{_escape_text(m.group(2).strip())}</h{level}>")
        elif stripped.strip():
            out.append(f"<p>{_escape_text(stripped.strip())}</p>")
    return "\n".join(out)


def render_document(
    title: str,
    md_text: str,
    *,
    lang: str,
    epub_type: str = "bodymatter",
) -> str:
    """渲染完整 XHTML 内容文档。"""
    body = markdown_to_xhtml(md_text)
    return _wrap_xhtml(title, body, lang=lang, epub_type=epub_type)


def _wrap_xhtml(
    title: str,
    body: str,
    *,
    lang: str,
    epub_type: str = "bodymatter",
) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}" '
        f'epub:prefix="epub: http://www.idpf.org/vocab/package/#">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        f"<title>{_escape_text(title)}</title>\n"
        "</head>\n"
        f'<body epub:type="{epub_type}">\n'
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def render_bilingual_document(
    title: str,
    rows: list[dict],
    *,
    lang_src: str,
    lang_tgt: str,
    order: str = "target_first",
) -> str:
    """按句级对照表渲染双语 XHTML（源/译交错，顺序由 order 决定）。"""
    blocks: list[str] = []
    for r in rows:
        src = _escape_text(r.get("src", ""))
        tgt = _escape_text(r.get("tgt", ""))
        src_p = f'<p class="src" xml:lang="{lang_src}">{src}</p>'
        tgt_p = f'<p class="tgt" xml:lang="{lang_tgt}">{tgt}</p>'
        pair = f"{tgt_p}\n{src_p}" if order == "target_first" else f"{src_p}\n{tgt_p}"
        blocks.append(pair)
    body = "\n".join(blocks) if blocks else ""
    return _wrap_xhtml(title, body, lang=lang_tgt)


def slug_file(unit_id: str) -> str:
    """把单元 ID 转为安全文件名（稳定、ASCII）。"""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", unit_id)
    return safe or "unit"


def structured_to_content(
    structured: Path,
    unit_id: str,
    *,
    lang: str,
    epub_type: str,
) -> tuple[str, str]:
    """读取 structured 单元 md 文件，返回 (filename, xhtml 内容)。"""
    md_text = structured.read_text(encoding="utf-8")
    title = Path(structured.stem).name
    filename = f"{slug_file(unit_id)}.xhtml"
    xhtml = render_document(title, md_text, lang=lang, epub_type=epub_type)
    return filename, xhtml