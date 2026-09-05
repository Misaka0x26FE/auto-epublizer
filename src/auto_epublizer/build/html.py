"""XHTML 渲染：markdown → XHTML 正文、单页文档、双语文档、文件名 slug。

本模块只做**确定性纯函数**渲染：给定 markdown / 对照行，产出完整 XHTML 字符串，
不做任何网络或文件 IO。图片引用（``![](media/…)``）按传入路径原样保留为
``<img src>``，由上层（orchestrator）负责把媒体字节收集进 EPUB。

脚注语义化（epub-template-spec §6）：pandoc 脚注语法 ``[^label]`` 引用 →
``<a epub:type="noteref">``，``[^label]: 文本`` 定义 → 章末
``<aside epub:type="footnote">``；编号经 ``FootnoteState`` 跨单元全局连续，
注码/注释双向跳转。呈现样式不设（字体/颜色/字号交阅读器）。
"""

from __future__ import annotations

import re
from html import escape

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# pandoc 的「缩略图链接图片」语法：
#   [[![alt](src){attrs}](href "title"){.mw-file-description}]{typeof="mw:File"}
# 归一为标准 markdown 图片（src 保留），避免内层 <img> 被外层链接二次转义。
_PANDOC_LINKED_IMG = re.compile(r"\[\[!\[([^\]]*)\]\(([^)]+)\)[^\]]*\]\([^)]*\)[^\]]*\]\{[^}]*\}")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_DANGEROUS_URL = re.compile(r"^\s*(?:javascript|data|vbscript):", re.IGNORECASE)
# pandoc 脚注：行内引用 [^label]；定义块 [^label]: 文本（可带缩进续行）
_FN_REF = re.compile(r"\[\^([^\]\s]+)\]")
_FN_DEF = re.compile(r"^\[\^([^\]\s]+)\]:\s*(.*)$")
# pandoc 从 MediaWiki 转出时的排版残留标记：
# - 容器 div：`:::`、`::: gallerytext`、`::: {.thumb …}`、`-   ::: {…}`
# - 纯反斜杠装饰行：`\`
_CONTAINER_LINE = re.compile(r"^\s*-*\s*:+\s*(?:\{[^}]*\}|[a-zA-Z][a-zA-Z ]*)?\s*$")
_SLASH_LINE = re.compile(r"^\s*\\\s*$")


class FootnoteState:
    """跨单元全局脚注编号器（构建期共享；按文中首次出现顺序连续编号）。"""

    def __init__(self) -> None:
        self._numbers: dict[tuple[str, str], int] = {}
        self._next = 0

    def number(self, unit_id: str, label: str) -> int:
        """取（或分配）某单元某标签的全局序号。"""
        key = (unit_id, label)
        if key not in self._numbers:
            self._next += 1
            self._numbers[key] = self._next
        return self._numbers[key]

    def has(self, unit_id: str, label: str) -> bool:
        return (unit_id, label) in self._numbers


def _split_footnote_defs(md: str) -> tuple[str, dict[str, str]]:
    """摘出脚注定义块，返回 (去掉定义的正文, {label: 定义文本})。

    定义 = 匹配 ``[^label]: 文本`` 的行 + 随后非空续行（直到空行/下一定义/正文）。
    """
    defs: dict[str, str] = {}
    body_lines: list[str] = []
    current: str | None = None
    for line in md.splitlines():
        m = _FN_DEF.match(line)
        if m:
            label = str(m.group(1))
            defs[label] = m.group(2).strip()
            current = label
            continue
        if current is not None:
            label = current
            if line.strip() and not line.startswith("#"):
                defs[label] = f"{defs[label]} {line.strip()}".strip()
                continue
            current = None
            if not line.strip():
                continue  # 定义块后的空行不进正文
        body_lines.append(line)
    return "\n".join(body_lines), defs


def _substitute_noterefs(
    xhtml: str, unit_id: str, defs: dict[str, str], fn_state: FootnoteState | None
) -> str:
    """把 XHTML 里的字面 ``[^label]`` 替换为 noteref 锚点（无定义则保留字面）。"""
    if "^" not in xhtml:
        return xhtml

    def _sub(m: re.Match[str]) -> str:
        label = m.group(1)
        if label not in defs or fn_state is None:
            return m.group(0)
        n = fn_state.number(unit_id, label)
        return (
            f'<sup class="noteref"><a epub:type="noteref" id="ref-{n}" href="#fn-{n}">{n}</a></sup>'
        )

    return _FN_REF.sub(_sub, xhtml)


def _render_footnote_section(items: list[tuple[int, str]]) -> str:
    """渲染章末脚注区：``[(全局序号, 定义文本)]`` → aside（epub:type=footnote，带回链）。"""
    asides: list[str] = []
    for n, text in items:
        body = _inline(escape(text))
        asides.append(
            f'<aside epub:type="footnote" id="fn-{n}" role="doc-footnote">'
            f'<p>{body} <a epub:type="backlink" href="#ref-{n}">↩</a></p></aside>'
        )
    return (
        '<section class="footnotes" epub:type="footnotes">\n' + "\n".join(asides) + "\n</section>"
    )


def _clean_pandoc_markers(md: str) -> str:
    """清理 pandoc 转出时的排版残留（确定性纯函数）：
    - 删除容器 div 标记行（:::/::: gallerytext/::: {.thumb …}/- ::: {…}）
    - 删除纯反斜杠装饰行（\\）
    - MediaWiki 引用标记（\\> / \\>\\>）→「——」（贴合中文小说场景提示排版）
    """
    cleaned = []
    for line in md.splitlines():
        s = line.strip()
        if _CONTAINER_LINE.match(s) or _SLASH_LINE.match(s):
            continue
        line = line.replace("\\>\\>", "——").replace("\\>", "——")
        cleaned.append(line)
    return "\n".join(cleaned)


def _render_img(alt: str, src: str) -> str:
    """行内图片 → <img>：限宽防溢出、块级居中（功能性样式）；危险 URL 降级为空。"""
    src = src.strip()
    if _DANGEROUS_URL.match(src):
        return ""
    # 空 alt 兜底为文件名（纯计算，不 IO）：MediaWiki 系源站图片常无 alt，
    # 空 alt 会被审计 W_IMG_NO_ALT 标记；agent 可在译文里显式写 alt 覆盖。
    alt = alt.strip() or _fallback_alt(src)
    return (
        f'<img src="{escape(src, quote=True)}" alt="{escape(alt, quote=True)}" '
        'style="max-width:100%;height:auto;display:block;margin:1em auto;"/>'
    )


def _fallback_alt(src: str) -> str:
    """从图片路径取可读文件名作兜底 alt：取 basename 并去扩展名。"""
    from pathlib import PurePath

    return PurePath(src.split("?", 1)[0]).name.rsplit(".", 1)[0] or src


def _inline(text: str) -> str:
    """行内 markdown → XHTML；危险 URL（javascript:/data:）降级为纯文本。"""

    def _img(m: re.Match[str]) -> str:
        return _render_img(m.group(1), m.group(2))

    def _link(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2).strip()
        if _DANGEROUS_URL.match(href):
            return escape(label)
        return f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'

    text = _IMG_RE.sub(_img, text)
    text = _LINK_RE.sub(_link, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    text = _CODE_RE.sub(r"<code>\1</code>", text)
    return text


# 图注段落：整段仅一张图且 alt 非空 → figure + figcaption（postprocessing-spec P1）
_IMG_ONLY_BLOCK = re.compile(r"^!\[([^\]]+)\]\(([^)]+)\)\s*$")
# 语义标签（epub-template-spec P2）：引用块 / 诗行块 / 列表
_BQ_LINE = re.compile(r"^\s*>\s?(.*)$")
_VERSE_LINE = re.compile(r"^\s*\|\s?(.*)$")
_UL_LINE = re.compile(r"^\s*[-*]\s+(.*)$")
_OL_LINE = re.compile(r"^\s*\d{1,3}[.、)]\s+(.*)$")


def markdown_to_xhtml(md: str, *, unit_id: str = "", fn_state: FootnoteState | None = None) -> str:
    """把 markdown 正文转换为 XHTML 片段（h1–h6 / p / figure，文本统一转义）。

    ``unit_id`` + ``fn_state`` 提供时启用脚注语义化：``[^label]`` → noteref、
    定义块 → 章末 aside，全局序号跨单元连续。
    """
    md = _clean_pandoc_markers(md)
    md = _PANDOC_LINKED_IMG.sub(lambda m: f"![{m.group(1)}]({m.group(2).strip()})", md)
    md, fn_defs = _split_footnote_defs(md)
    fn_items: list[tuple[int, str]] = []
    if fn_state is not None and fn_defs:
        # 全局编号：先按正文引用出现顺序，再按定义顺序补漏（未被引用的定义也入列）
        seen: set[str] = set()
        for m in _FN_REF.finditer(md):
            label = m.group(1)
            if label in fn_defs and label not in seen:
                seen.add(label)
                fn_items.append((fn_state.number(unit_id, label), fn_defs[label]))
        for label, text in fn_defs.items():
            if label not in seen:
                fn_items.append((fn_state.number(unit_id, label), text))
        fn_items.sort(key=lambda t: t[0])
    out: list[str] = []
    for block in re.split(r"\n\s*\n", md):
        block = block.strip("\n")
        if not block.strip():
            continue
        m_img = _IMG_ONLY_BLOCK.match(block.strip())
        if m_img:
            # 图注段落：figure + figcaption（alt 即图注）
            out.append(
                f'<figure class="imgfig">{_render_img(m_img.group(1), m_img.group(2))}'
                f"<figcaption>{escape(m_img.group(1))}</figcaption></figure>"
            )
            continue
        lines = block.splitlines()
        non_empty = [line for line in lines if line.strip()]
        # 语义标签（epub-template-spec P2）：引用 / 诗行 / 列表保留原生元素
        if non_empty and all(_BQ_LINE.match(line) for line in non_empty):
            inner = "\n".join(
                (_BQ_LINE.match(line).group(1) or "").strip()  # type: ignore[union-attr]
                for line in non_empty
            ).strip()
            if inner:
                out.append(f"<blockquote><p>{_inline(escape(inner))}</p></blockquote>")
                continue
        if non_empty and all(_VERSE_LINE.match(line) for line in non_empty):
            vlines = [
                (_VERSE_LINE.match(line).group(1) or "").strip()  # type: ignore[union-attr]
                for line in non_empty
            ]
            body = "<br/>".join(_inline(escape(v)) for v in vlines if v)
            if body:
                out.append(f'<p class="verse">{body}</p>')
                continue
        if non_empty and all(_UL_LINE.match(line) for line in non_empty):
            lis = "".join(
                f"<li>{_inline(escape(_UL_LINE.match(line).group(1).strip()))}</li>"  # type: ignore[union-attr]
                for line in non_empty
            )
            out.append(f"<ul>{lis}</ul>")
            continue
        if non_empty and all(_OL_LINE.match(line) for line in non_empty):
            lis = "".join(
                f"<li>{_inline(escape(_OL_LINE.match(line).group(1).strip()))}</li>"  # type: ignore[union-attr]
                for line in non_empty
            )
            out.append(f"<ol>{lis}</ol>")
            continue
        m = _HEADING_RE.match(lines[0])
        if m:
            level = min(len(m.group(1)), 6)
            out.append(f"<h{level}>{_inline(escape(m.group(2)))}</h{level}>")
            rest = "\n".join(lines[1:]).strip()
            if rest:
                out.append(f"<p>{_inline(escape(rest))}</p>")
        else:
            rendered = f"<p>{_inline(escape(block))}</p>"
            if "<img" in rendered:
                # 图片段落：不加首行缩进、居中（class=imgp 由 style.css 控制）
                rendered = rendered.replace("<p>", '<p class="imgp">', 1)
            out.append(rendered)
    if fn_state is not None and fn_defs:
        body = "\n".join(out)
        body = _substitute_noterefs(body, unit_id, fn_defs, fn_state)
        body += "\n" + _render_footnote_section(fn_items)
        return body
    return "\n".join(out)


def _page(title: str, body: str, *, lang: str) -> str:
    """组装一页完整 XHTML 文档（恰好一个 h1 位于 body 首行由调用方保证）。"""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" '
        f'xml:lang="{escape(lang, quote=True)}" '
        f'lang="{escape(lang, quote=True)}">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        '<link rel="stylesheet" type="text/css" href="style.css"/>\n'
        f"<title>{escape(title)}</title>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def render_document(
    title: str,
    md_text: str,
    *,
    lang: str,
    unit_id: str = "",
    fn_state: FootnoteState | None = None,
) -> str:
    """渲染一页纯译文文档（md_text 为结构化单元 markdown）。

    ``unit_id`` + ``fn_state`` 提供时启用脚注语义化（epub-template-spec §6）。
    """
    body = markdown_to_xhtml(md_text, unit_id=unit_id, fn_state=fn_state)
    return _page(title, body, lang=lang)


def render_bilingual_document(
    title: str,
    rows: list[dict],
    *,
    lang_src: str,
    lang_tgt: str,
    order: str = "target_first",
) -> str:
    """渲染一页双语对照文档：每句源/译段落上下交错，class=src/tgt。"""
    pairs: list[str] = []
    for r in rows:
        src, tgt = r.get("src", ""), r.get("tgt", "")
        if order == "target_first":
            pairs.append(f'<p class="tgt" lang="{escape(lang_tgt, quote=True)}">{escape(tgt)}</p>')
            pairs.append(f'<p class="src" lang="{escape(lang_src, quote=True)}">{escape(src)}</p>')
        else:
            pairs.append(f'<p class="src" lang="{escape(lang_src, quote=True)}">{escape(src)}</p>')
            pairs.append(f'<p class="tgt" lang="{escape(lang_tgt, quote=True)}">{escape(tgt)}</p>')
    return _page(title, "\n".join(pairs), lang=lang_tgt)


def slug_file(unit_id: str) -> str:
    """把稳定单元 ID 转成安全的文件名 slug（保留字母数字/连字符/下划线）。"""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", unit_id).strip("-")
    return slug or "unit"
