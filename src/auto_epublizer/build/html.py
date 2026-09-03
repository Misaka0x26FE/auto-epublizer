"""XHTML 渲染：markdown → XHTML 正文、单页文档、双语文档、文件名 slug。

本模块只做**确定性纯函数**渲染：给定 markdown / 对照行，产出完整 XHTML 字符串，
不做任何网络或文件 IO。图片引用（``![](media/…)``）按传入路径原样保留为
``<img src>``，由上层（orchestrator）负责把媒体字节收集进 EPUB。
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
# pandoc 从 MediaWiki 转出时的排版残留标记：
# - 容器 div：`:::`、`::: gallerytext`、`::: {.thumb …}`、`-   ::: {…}`
# - 纯反斜杠装饰行：`\`
_CONTAINER_LINE = re.compile(r"^\s*-*\s*:+\s*(?:\{[^}]*\}|[a-zA-Z][a-zA-Z ]*)?\s*$")
_SLASH_LINE = re.compile(r"^\s*\\\s*$")


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


def _inline(text: str) -> str:
    """行内 markdown → XHTML；危险 URL（javascript:/data:）降级为纯文本。"""

    def _img(m: re.Match[str]) -> str:
        alt, src = m.group(1), m.group(2).strip()
        if _DANGEROUS_URL.match(src):
            return ""
        # 限宽防溢出：max-width 100%，高度自适应，块级居中
        return (
            f'<img src="{escape(src, quote=True)}" alt="{escape(alt, quote=True)}" '
            'style="max-width:100%;height:auto;display:block;margin:1em auto;"/>'
        )

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


def markdown_to_xhtml(md: str) -> str:
    """把 markdown 正文转换为 XHTML 片段（h1–h6 / p，文本统一转义）。"""
    md = _clean_pandoc_markers(md)
    md = _PANDOC_LINKED_IMG.sub(lambda m: f"![{m.group(1)}]({m.group(2).strip()})", md)
    out: list[str] = []
    for block in re.split(r"\n\s*\n", md):
        block = block.strip("\n")
        if not block.strip():
            continue
        lines = block.splitlines()
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
    return "\n".join(out)


def _page(title: str, body: str, *, lang: str) -> str:
    """组装一页完整 XHTML 文档（恰好一个 h1 位于 body 首行由调用方保证）。"""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{escape(lang, quote=True)}" '
        f'lang="{escape(lang, quote=True)}">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        '<link rel="stylesheet" type="text/css" href="style.css"/>\n'
        f"<title>{escape(title)}</title>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def render_document(title: str, md_text: str, *, lang: str) -> str:
    """渲染一页纯译文文档（md_text 为结构化单元 markdown）。"""
    body = markdown_to_xhtml(md_text)
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
