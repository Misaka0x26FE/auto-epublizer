# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""XHTML 渲染：markdown → XHTML 正文、单页文档、文件名 slug。

本模块只做**确定性纯函数**渲染：给定 markdown，产出完整 XHTML 字符串，
不做任何网络或文件 IO。图片引用（``![](media/…)``）按传入路径原样保留为
``<img src>``，由上层（orchestrator）负责把媒体字节收集进 EPUB。

脚注语义化（epub-template-spec §6）：pandoc 脚注语法 ``[^label]`` 引用 →
``<a epub:type="noteref">``，``[^label]: 文本`` 定义 → 章末
``<aside epub:type="footnote">``；注码 ``[N]`` 按章独立编号（每单元一份
``FootnoteState``，从 1 起），注码/注释双向跳转。呈现样式不设（字体/颜色/字号交阅读器）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# pandoc 的「缩略图链接图片」语法：
#   [[![alt](src){attrs}](href "title"){.mw-file-description}]{typeof="mw:File"}
# 归一为标准 markdown 图片（src 保留），避免内层 <img> 被外层链接二次转义。
_PANDOC_LINKED_IMG = re.compile(r"\[\[!\[([^\]]*)\]\(([^)]+)\)[^\]]*\]\([^)]*\)[^\]]*\]\{[^}]*\}")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# 正文导航锚点：[]{#page_15}（ingest 保留的源 <a id>）→ 空锚点元素，供内部链接跳转。
# 两处放宽，均不放开 id 字符集：
#   ① `#` 允许缺省：抽取器会丢属性里的井号，源侧并存 `[]{#GBS.0014.04}` 与
#      `[]{GBS.0014.05}`（Pentagon Papers 329 处）。
#   ② `[]` 与 `{` 之间允许空格：抽取噪声 `[] {#GBS.0053.02}`（Pentagon 29 处）。
#      用 `[ \t]*` 而非 `\s*`，免得跨行吞掉后面的段落。
# id 字符集**始终不含空格**——`[]{#word illegible}` 是校勘标记而非锚点，
# 放宽会让它变成空锚点，等于悄悄删掉标记（比显示乱码更糟，见缺陷清单 pentagon ch05）。
_ANCHOR_INLINE_RE = re.compile(r"\[\][ \t]*\{#?([\w:.-]+)\}")
# 空属性块 `{[]}`：只裹一个空 span 的 pandoc 属性表，无信息（见 `_inline` 里的说明）
_EMPTY_ATTR_RE = re.compile(r"\{[ \t]*\[[ \t]*\][ \t]*\}")
# 标题上的 id 属性：``标题 {#ch01}`` → (标题, ch01)
_HEADING_ID_RE = re.compile(r"\s*\{#([\w:.-]+)\}\s*$")
_BOLD_RE = re.compile(r"\*\*((?:[^*]|\\\*)+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
# pandoc 反斜杠转义：`\(` / `\.` / `\[` / `\*` / `\\` → 字面标点（转义符本身不输出）。
# 缺失时源里的出版方编辑插入 `\[一年后……\]`、CIP 行 `p\. cm.`、编号 `\(1\)`
# 会带着**可见反斜杠**进成品（四本书合计 1000+ 处；audit 的 W_RESIDUE
# 不检查该形态，故此前从未告警）。
# 可转义集按 pandoc 规则取 ASCII 标点全集；落点须在链接/锚点/强调替换**之后**
# ——先脱转义会让 `\[x\](u)` 被 `_LINK_RE` 误判成链接。
_ESCAPED_PUNCT_RE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])")
# 代码段内的反斜杠是字面内容（与 pandoc 一致），须跳过不脱转义
_CODE_SPAN_SPLIT_RE = re.compile(r"(`[^`]+`)")
_DANGEROUS_URL = re.compile(r"^\s*(?:javascript|data|vbscript):", re.IGNORECASE)
# pandoc 脚注：行内引用 [^label]；定义块 [^label]: 文本（可带缩进续行）
_FN_REF = re.compile(r"\[\^([^\]\s]+)\]")
_FN_DEF = re.compile(r"^\[\^([^\]\s]+)\]:\s*(.*)$")
# pandoc 从 MediaWiki 转出时的排版残留标记：
# - 容器 div：`:::`、`::: gallerytext`、`::: {.thumb …}`、`::: bq1`、`:::[]{#id}`、`-   ::: {…}`
# 类名允许数字/下划线/连字符（`bq1`、`part1`），并允许 `[]` 属性前缀（`:::[]{#id}`）；
# 二者缺失时栅栏会作为正文漏进成品（Pentagon Papers 回归，audit 报 W_RESIDUE）。
# - 纯反斜杠装饰行：`\`
_CONTAINER_LINE = re.compile(
    r"^\s*-*\s*:+\s*(?:\[[^\]]*\])?(?:\{[^}]*\}|[a-zA-Z][a-zA-Z0-9_.-]*)?\s*$"
)
# 容器行上的显式锚点 id（::: {#page0026} / :::[]{#GBS.0829.04} / ::: {#calibre_pb_10}）
_CONTAINER_ID_RE = re.compile(r"^\s*-*\s*:+\s*(?:\[[^\]]*\])?\{#([\w:.-]+)\}\s*$")
_SLASH_LINE = re.compile(r"^\s*\\\s*$")


class FootnoteState:
    """脚注编号器（每单元新建一份；按章内首次出现顺序从 1 起连续编号）。"""

    def __init__(self) -> None:
        self._numbers: dict[tuple[str, str], int] = {}
        self._next = 0

    def number(self, unit_id: str, label: str) -> int:
        """取（或分配）某单元某标签的章内序号。"""
        key = (unit_id, label)
        if key not in self._numbers:
            self._next += 1
            self._numbers[key] = self._next
        return self._numbers[key]

    def has(self, unit_id: str, label: str) -> bool:
        return (unit_id, label) in self._numbers


# ── N 阶段：结构化注释渲染（notes.json → noteref/footnote + 跨文件回链）──────

_NOTE_MARKER_RE = re.compile(r"\[\^(ref-\d{6,})\]")


@dataclass(frozen=True)
class NoteRef:
    """一条已登记引用的渲染信息：显示号（按作用域确定）与所属注文。"""

    ref_id: str
    note_id: str
    number: int


@dataclass(frozen=True)
class NoteItem:
    """宿主单元要渲染的注文：完整 Markdown + 全部引用回链（一注多引/跨文件）。"""

    note_id: str
    number: int
    text_md: str
    backlinks: tuple[str, ...]  # ["ch01.xhtml#ref-000001", ...]


def _substitute_note_markers(
    xhtml: str,
    refs: dict[str, NoteRef],
    href_by_note: dict[str, str],
) -> str:
    """把字面 ``[^ref-…]`` 替换为标准 noteref 锚点；href 指向注文宿主文件的 aside。

    未进计划的标记保留字面（登记门/导入门已保证不会发生；保留便于审计定位而非静默丢弃）。
    """
    if "^ref-" not in xhtml:
        return xhtml

    def _sub(m: re.Match[str]) -> str:
        rid = m.group(1)
        r = refs.get(rid)
        if r is None:
            return m.group(0)
        target = href_by_note.get(r.note_id, "")
        href = f"{target}#fn-{r.note_id}" if target else f"#fn-{r.note_id}"
        return (
            f'<sup class="noteref"><a epub:type="noteref" role="doc-noteref" '
            f'id="{rid}" href="{escape(href, quote=True)}">[{r.number}]</a></sup>'
        )

    return _NOTE_MARKER_RE.sub(_sub, xhtml)


def _render_notes_section(items: list[NoteItem]) -> str:
    """渲染宿主单元的注释区：完整块级 Markdown + 每条引用独立回链。"""
    asides: list[str] = []
    for it in items:
        body = markdown_to_xhtml(it.text_md, unit_id="")
        backs = " ".join(
            f'<a epub:type="backlink" href="{escape(b, quote=True)}">↩</a>' for b in it.backlinks
        )
        asides.append(
            f'<aside epub:type="footnote" id="fn-{it.note_id}" role="doc-footnote">'
            f"<p>[{it.number}]</p>\n{body}\n<p>{backs}</p></aside>"
        )
    return (
        '<section class="footnotes" epub:type="footnotes">\n' + "\n".join(asides) + "\n</section>"
    )


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
    """把 XHTML 里的字面 ``[^label]`` 替换为 noteref 锚点（无定义则保留字面）。

    **同一脚注被重复引用时，锚点 id 必须去重**（2026-10-08 reichsarbeitsministerium
    essay-07 实测）：德文史学著作里「见前引注 6」式的重复引用很常见，原实现对每次
    出现都发同一个 ``id="ref-6"``，epubcheck 直接报 RSC-005
    ``Duplicate ID "ref-6"``（2 处 error，阻断放行）。

    口径：同一单元内某标签的第 k 次引用，id 取 ``ref-{n}``（k=1）或
    ``ref-{n}-{k}``（k≥2）。章末 backlink 的 ``href="#ref-{n}"`` 仍落在
    **首次**引用上——重复引用没有独立回链目标，指向首次引用才是正确语义。
    """
    if "^" not in xhtml:
        return xhtml

    seen: dict[str, int] = {}

    def _sub(m: re.Match[str]) -> str:
        label = m.group(1)
        if label not in defs or fn_state is None:
            return m.group(0)
        n = fn_state.number(unit_id, label)
        k = seen.get(label, 0) + 1
        seen[label] = k
        rid = f"ref-{n}" if k == 1 else f"ref-{n}-{k}"
        return (
            f'<sup class="noteref"><a epub:type="noteref" role="doc-noteref" '
            f'id="{rid}" href="#fn-{n}">[{n}]</a></sup>'
        )

    return _FN_REF.sub(_sub, xhtml)


def _render_footnote_section(items: list[tuple[int, str]]) -> str:
    """渲染章末脚注区：``[(章内序号, 定义文本)]`` → aside（epub:type=footnote，带回链）。"""
    asides: list[str] = []
    for n, text in items:
        body = _inline(escape(text))
        asides.append(
            f'<aside epub:type="footnote" id="fn-{n}" role="doc-footnote">'
            f'<p>[{n}] {body} <a epub:type="backlink" href="#ref-{n}">↩</a></p></aside>'
        )
    return (
        '<section class="footnotes" epub:type="footnotes">\n' + "\n".join(asides) + "\n</section>"
    )


def _split_heading_blocks(block: str) -> list[str]:
    """块内二次切分：在**每个** ATX 标题行处切开，使每块各自以标题起头。

    CommonMark 规定 ATX 标题可打断段落，但单纯按空行切块做不到——源抽取与
    MinerU OCR 常丢失标题前的空行（实测 parliamentary-socialism 全书 33 处，
    如题词「…Ramsay MacDonald, 1909」下一行紧跟 ``## 1. THE LIBERAL CONNECTION``）。
    标题遂成为懒续行，被整体塞进 ``<p>``，读者直接看到字面 ``## 1. 与自由党的联系``。

    切点必须**包含块首**（``i == 0``）才覆盖连续标题行 ``## A`` / ``### B``：
    否则 ``## A`` 仍会命中块首标题分支、把 ``### B`` 当作其后正文塞进 ``<p>``
    （实测 matla-al-sadayn-1 3 处、nazi-crimes-occupied-ussr-1 1 处）。

    与 ``_MD_RESIDUE`` 的关系：审计原先只检查裸 ``##`` 是否整行出现，块首命中即放行，
    故本形态**检测层与渲染层同时漏**（parliamentary-socialism 33 处零告警）。
    围栏代码块内不切分（```` ``` ```` 内的 ``#`` 是内容不是标题）。
    """
    lines = block.splitlines()
    starts: list[int] = []
    fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if _HEADING_RE.match(line):
            starts.append(i)
    if not starts:
        return [block]
    parts: list[str] = []
    prev = 0
    for i in starts:
        part = "\n".join(lines[prev:i]).strip("\n")
        if part.strip():
            parts.append(part)
        prev = i
    parts.append("\n".join(lines[prev:]).strip("\n"))
    return [p for p in parts if p.strip()]


def _iter_blocks(md: str) -> list[str]:
    """按空行切块 + 块内 ATX 标题二次切分。

    ``markdown_to_xhtml`` 与 ``subheading_anchors`` **必须**共用本函数：
    前者产出 ``id``、后者产出 nav 锚点，两套规则一旦分叉，目录链接即悬空。
    """
    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n", md):
        block = raw.strip("\n")
        if not block.strip():
            continue
        blocks.extend(_split_heading_blocks(block))
    return blocks


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
            # 带 {#id} 的容器行承载源文档的页码/位置锚点（如 ::: {#page0026}）：
            # 删除栅栏本身，但保留一个等价的内联锚点，供目录与交叉引用跳转。
            m_anchor = _CONTAINER_ID_RE.match(s)
            if m_anchor:
                cleaned.append(f"[]{{#{m_anchor.group(1)}}}")
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
    # 调用方契约：_render_img 收到的 alt/src 已经过 escape()（与 _inline 的文本同源），
    # 此处不再转义，避免 &quot; 等实体被二次转义（&amp;quot;）。
    return (
        f'<img src="{src}" alt="{alt}" '
        'style="max-width:100%;height:auto;display:block;margin:1em auto;"/>'
    )


def _fallback_alt(src: str) -> str:
    """从图片路径取可读文件名作兜底 alt：取 basename 并去扩展名。"""
    from pathlib import PurePath

    return PurePath(src.split("?", 1)[0]).name.rsplit(".", 1)[0] or src


def _split_heading_id(text: str) -> tuple[str, str | None]:
    """拆分标题末尾的 ``{#id}`` 属性，返回 (纯标题, id|None)。

    pandoc 的行内锚点形态是 ``[]{#id}``（空方括号 + 属性），标题上两者常连用：
    ``### **# 1**[]{#d1}``。只剥 ``{#d1}`` 会把空 ``[]`` 留给读者，渲染成
    ``<h3 id="d1"><strong># 1</strong>[]</h3>``（Pentagon Papers 135 处正文标题 +
    134 处 nav 标签）。故连同其前的 ``[]`` 一并吃掉。
    """
    m = _HEADING_ID_RE.search(text)
    if not m:
        return text, None
    head = text[: m.start()].rstrip()
    if head.endswith("[]"):
        head = head[:-2].rstrip()
    return head, m.group(1)


# 目录（nav）标签用的行内 markdown 剥离：nav 标签是纯文本，不经 _inline 渲染，
# 故须在此去掉强调与行内锚点，否则读者在目录里看到字面 `**`、`[]{#…}`
# （Pentagon Papers 全书 83% 标题行含 markdown；W_RESIDUE 豁免 nav.xhtml）。
_LABEL_ANCHOR = re.compile(r"\{[^{}]*\}")  # 裸 {…} 属性块（含 {#id}）
# pandoc 行内属性形态 `[]{#id}` / `[文本]{attrs}`：先吃掉方括号包裹再剥属性。
# `[]` 与 `{` 之间允许空格（抽取噪声 `[] {#id}`，Pentagon Papers 29 处）
_LABEL_INLINE_ATTR = re.compile(r"\[([^\]]*)\][ \t]*\{[^{}]*\}")
_LABEL_IMG = re.compile(r"!\[([^\]]*)\]\([^)]*\)")  # 图片 → 取 alt
_LABEL_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # 链接 → 取标签文本
_LABEL_EMPH = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1", re.S)
_LABEL_CODE = re.compile(r"`([^`]*)`")


def plain_label(text: str) -> str:
    """把标题/条目标题降为纯文本（用于 nav 标签等不渲染 markdown 的场合）。"""
    out = _LABEL_IMG.sub(r"\1", text or "")
    out = _LABEL_LINK.sub(r"\1", out)
    out = _LABEL_CODE.sub(r"\1", out)
    out = _LABEL_INLINE_ATTR.sub(r"\1", out)
    out = _LABEL_EMPH.sub(r"\2", out)
    out = _LABEL_ANCHOR.sub("", out)
    return re.sub(r"\s+", " ", _unescape_punct(out)).strip()


def _unescape_punct(text: str) -> str:
    """反斜杠转义 → 字面标点（代码段除外，其反斜杠是内容）。"""
    parts = _CODE_SPAN_SPLIT_RE.split(text)
    return "".join(p if i % 2 else _ESCAPED_PUNCT_RE.sub(r"\1", p) for i, p in enumerate(parts))


def _inline(text: str) -> str:
    """行内 markdown → XHTML；危险 URL（javascript:/data:）降级为纯文本。"""

    def _img(m: re.Match[str]) -> str:
        return _render_img(m.group(1), m.group(2))

    def _link(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2).strip()
        if _DANGEROUS_URL.match(href):
            return label
        # 注意：_inline 的所有调用方传入的文本已先经 escape()，label 不得再次转义，
        # 否则 &quot; 等实体会被二次转义成 &amp;quot; 直接显示给读者。
        return f'<a href="{escape(href, quote=True)}">{label}</a>'

    # 正文导航锚点 []{#id} / []{id} → <a id="id"></a>（id 已由白名单正则约束，无需转义）
    text = _ANCHOR_INLINE_RE.sub(r'<a id="\1"></a>', text)
    # 空属性块 `{[]}`：pandoc 转出噪声，属性表里只裹着一个空 span（Pentagon Papers
    # 142 处，源侧形态 `{[]}[]{#GBS.0682.04}`）。锚点已被上一行取出，包裹它的
    # 属性壳没有任何信息，留着就以字面 `{[]}` 印给读者。
    text = _EMPTY_ATTR_RE.sub("", text)
    text = _IMG_RE.sub(_img, text)
    text = _LINK_RE.sub(_link, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    # 脱转义放在结构替换之后、代码段转换之前：既不干扰链接/锚点/强调的识别，
    # 又能靠仍存在的反引号跳过代码段（其反斜杠是字面内容）
    text = _unescape_punct(text)
    text = _CODE_RE.sub(r"<code>\1</code>", text)
    return text


# 图注段落：整段仅一张图且 alt 非空 → figure + figcaption（postprocessing-spec P1）
_IMG_ONLY_BLOCK = re.compile(r"^!\[([^\]]+)\]\(([^)]+)\)\s*$")

# pandoc 原始 HTML：`` ```{=html} … ``` `` 围栏块，以及行内 `` `X`{=html} ``。
# 缺这一层时 `<div>` / `<svg>` 会被 escape 成 ``&lt;div&gt;`` 原样印给读者
# （2026-10-06 Thiriart 封面实测：整段 SVG 连同 `{=html}` 属性与游离反引号漏成乱码）。
_RAW_HTML_FENCE = re.compile(r"^\s*`{3,}\s*(?:\{=\s*html\s*\})?\s*$")
_RAW_HTML_INLINE = re.compile(r"`([^`]+)`\s*\{\s*=\s*html\s*\}")
_HTML_TAG_LINE = re.compile(r"^\s*(?:</?[A-Za-z][\w:.-]*(?:\s[^<>]*?)?/?>\s*)+$")


def _raw_html_block(block: str) -> str | None:
    """块内全是 pandoc 原始 HTML 时直通输出，否则返回 None 交常规渲染。

    白名单口径：去掉围栏与行内 raw 标记后，**每一行**都必须是纯 HTML 标签行。
    只要混进一行普通 markdown 就不认（宁可漏渲染，也不可把未转义文本放行）。
    """
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None
    kept: list[str] = []
    for line in lines:
        if _RAW_HTML_FENCE.match(line):
            continue
        kept.append(_RAW_HTML_INLINE.sub(r"\1", line).strip())
    if not kept:
        return None
    if not all(_HTML_TAG_LINE.match(ln) for ln in kept):
        return None
    # 保留原始缩进形态原样输出（SVG 属性换行等），仅去掉围栏与 raw 标记
    out: list[str] = []
    for line in lines:
        if _RAW_HTML_FENCE.match(line):
            continue
        out.append(_RAW_HTML_INLINE.sub(r"\1", line).strip())
    return "\n".join(out)


# 语义标签（epub-template-spec P2）：引用块 / 诗行块 / 列表
_BQ_LINE = re.compile(r"^\s*>\s?(.*)$")
_VERSE_LINE = re.compile(r"^\s*\|\s?(.*)$")
_UL_LINE = re.compile(r"^\s*[-*]\s+(.*)$")
_OL_LINE = re.compile(r"^\s*\d{1,3}[.、)]\s+(.*)$")
# 有序列表标记（分捕获组）：编号 / 分隔符 / 内容
_OL_MARK = re.compile(r"^\s*(\d{1,3})([.、)])\s+(.*)$")

# 表格：pandoc 简单/网格表（成排的 `---` 列界 + 内容行）与 md 管道表
_TABLE_DASH_ROW = re.compile(r"^\s*-{3,}(?:\s+-{3,})+\s*$")
_TABLE_EQ_ROW = re.compile(r"^\s*={3,}(?:\s+={3,})+\s*$")
_TABLE_DASH_SPAN = re.compile(r"-{3,}")
_PIPE_SEP_ROW = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _split_pipe_row(line: str) -> list[str]:
    body = line.strip().strip("|")
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


# 表格单元格里的 ATX 标记：GFM 表格单元内不允许块级标题，源抽取却常把小节标题
# 连同行内容一起吃进单元格（BLP 附录 2：`| **## 议会工党主席，1906—22** | |`）。
# 渲染层只能按字面输出，读者遂在表格里看到字面 `##`。
# 只吃**紧贴行首或紧贴行内 markdown 标记之后**的标记，避免误伤 `# 1` 这类
# 编号内容（Pentagon Papers 的文件号就在正文标题里，属正常内容）。
_CELL_ATX = re.compile(r"(?m)(^|(?<=\*\*)|(?<=\*)|(?<=`))#{1,6}[ \t]+")


def _cell(text: str) -> str:
    """单元格文本清洗：去掉无意义的 ATX 标记后交 `_inline` 渲染。"""
    return _inline(escape(_CELL_ATX.sub(r"\1", text)))


def _render_pipe_table(lines: list[str]) -> str:
    """md 管道表 → XHTML table（首行为表头，第二行为分隔行）。"""
    head = "".join(f"<th>{_cell(c)}</th>" for c in _split_pipe_row(lines[0]))
    rows = []
    for line in lines[2:]:
        if not line.strip() or "|" not in line:
            continue
        cells = _split_pipe_row(line)
        rows.append("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in cells) + "</tr>")
    return (
        '<table class="data"><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _dash_spans(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _TABLE_DASH_SPAN.finditer(line)]


def _split_span_row(line: str, spans: list[tuple[int, int]]) -> list[str]:
    r"""按列切开一个表格数据行。

    pandoc 按**原始**单元格宽度排版：清洗去掉 ``[text]{.class}`` 等属性会缩短
    单元格文本，使其后的列整体左移、固定列位错位（多列并成一列）。此时列间空白
    会变大（≥2 空格），故优先按 ``\s{2,}`` 切分恢复各列；若切分数与列数不符
    （例如单元格恰好填满列宽、列间只剩 1 空格），退回按 dash 行的固定列位切分。
    """
    parts = [c.strip() for c in re.split(r"\s{2,}", line.strip())]
    if len(parts) == len(spans):
        return parts
    cells: list[str] = []
    for i, (start, _end) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(line)
        cells.append(line[start:end].strip())
    return cells


def _render_simple_table(lines: list[str]) -> str | None:
    """pandoc 简单/网格表 → XHTML table。

    列界由首个 ``---`` 行的各段起止列位置确定；``===`` 行前为表头（无则首行作表头）。
    """
    borders = [i for i, ln in enumerate(lines) if _TABLE_DASH_ROW.match(ln)]
    if not borders:
        return None
    spans = _dash_spans(lines[borders[0]])
    if len(spans) < 2:
        return None
    eq_idx = next((i for i, ln in enumerate(lines) if _TABLE_EQ_ROW.match(ln)), None)
    content = [
        (i, ln)
        for i, ln in enumerate(lines)
        if not _TABLE_DASH_ROW.match(ln) and not _TABLE_EQ_ROW.match(ln) and ln.strip()
    ]
    if not content:
        return None
    if eq_idx is not None:
        header = [ln for i, ln in content if i < eq_idx]
        body = [ln for i, ln in content if i > eq_idx]
    else:
        header = [content[0][1]]
        body = [ln for _i, ln in content[1:]]

    def head_cells(line: str) -> str:
        return "".join(f"<th>{_cell(c)}</th>" for c in _split_span_row(line, spans))

    def body_cells(line: str) -> str:
        return "".join(f"<td>{_cell(c)}</td>" for c in _split_span_row(line, spans))

    return (
        '<table class="data"><thead>'
        + "".join(f"<tr>{head_cells(ln)}</tr>" for ln in header)
        + "</thead><tbody>"
        + "".join(f"<tr>{body_cells(ln)}</tr>" for ln in body)
        + "</tbody></table>"
    )


def _maybe_render_table(block: str) -> str | None:
    """块级表格渲染：管道表或 pandoc 简单/网格表；非表格返回 None。"""
    lines = block.splitlines()
    if len(lines) >= 2 and "|" in lines[0] and _PIPE_SEP_ROW.match(lines[1]) and "|" in lines[1]:
        return _render_pipe_table(lines)
    if any(_TABLE_DASH_ROW.match(ln) for ln in lines):
        return _render_simple_table(lines)
    return None


def markdown_to_xhtml(
    md: str,
    *,
    unit_id: str = "",
    fn_state: FootnoteState | None = None,
    note_refs: dict[str, NoteRef] | None = None,
    note_items: list[NoteItem] | None = None,
    href_by_note: dict[str, str] | None = None,
) -> str:
    """把 markdown 正文转换为 XHTML 片段（h1–h6 / p / figure，文本统一转义）。

    ``unit_id`` + ``fn_state`` 提供时启用旧记法脚注语义化：``[^label]`` → noteref、
    定义块 → 章末 aside，章内序号从 1 起独立编号。

    ``note_refs`` + ``note_items``（N 阶段）启用**结构化注释**：正文
    ``[^ref-…]`` → 标准 noteref（跨文件 href 由 ``href_by_note`` 给出），宿主单元
    末尾渲染完整注文（一注多引各自回链）。与旧记法互不干扰（标记前缀不同）。
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
    hcount = 0  # level≥2 标题计数（与 subheading_anchors 同规则，保证 nav 锚点不悬空）
    for block in _iter_blocks(md):
        block = block.strip("\n")
        if not block.strip():
            continue
        raw_html = _raw_html_block(block)
        if raw_html is not None:
            out.append(raw_html)
            continue
        table = _maybe_render_table(block)
        if table is not None:
            out.append(table)
            continue
        m_img = _IMG_ONLY_BLOCK.match(block.strip())
        if m_img:
            # 图注段落：figure + figcaption（alt 即图注）
            out.append(
                f'<figure class="imgfig">{_render_img(escape(m_img.group(1), quote=True), escape(m_img.group(2), quote=True))}'
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
            marks = [_OL_MARK.match(line) for line in non_empty]
            nums = [int(m.group(1)) for m in marks if m]
            delims = {m.group(2) for m in marks if m}
            # 仅「编号 1 起连续递增 + `. / 、` 分隔」的块按真有序列表渲染（<ol> 自动编号
            # 恰好与原编号一致）。其余（如校异/脚注式 `1) 2) 5)…`，数字是真实注号）：
            # <ol> 自动编号会整体重写为 1,2,3…，隔断的单条块甚至会全部显示为 1——
            # 必须保留原文数字、按普通段落输出。
            if nums == list(range(1, len(nums) + 1)) and delims <= {".", "、"}:
                lis = "".join(
                    f"<li>{_inline(escape(m.group(3).strip()))}</li>"  # type: ignore[union-attr]
                    for m in marks
                )
                out.append(f"<ol>{lis}</ol>")
            else:
                body = "<br/>".join(_inline(escape(line.strip())) for line in non_empty)
                out.append(f'<p class="fnlist">{body}</p>')
            continue
        m = _HEADING_RE.match(lines[0])
        if m:
            level = min(len(m.group(1)), 6)
            heading, hid = _split_heading_id(m.group(2))
            if level >= 2 and unit_id:
                # 单元内子标题自动稳定 id（nav 锚点用）：显式 {#id} 优先，
                # 缺省 {unit_id}-h{n}；计数含显式 id 者（与扫描器规则一致）
                hcount += 1
                hid = hid or f"{unit_id}-h{hcount}"
            id_attr = f' id="{hid}"' if hid else ""
            out.append(f"<h{level}{id_attr}>{_inline(escape(heading))}</h{level}>")
            rest = "\n".join(lines[1:]).strip()
            if rest:
                out.append(f"<p>{_inline(escape(rest))}</p>")
        else:
            rendered = f"<p>{_inline(escape(block))}</p>"
            if "<img" in rendered:
                # 图片段落：不加首行缩进、居中（class=imgp 由 style.css 控制）
                rendered = rendered.replace("<p>", '<p class="imgp">', 1)
            out.append(rendered)
    body = "\n".join(out)
    if fn_state is not None and fn_defs:
        body = _substitute_noterefs(body, unit_id, fn_defs, fn_state)
        body += "\n" + _render_footnote_section(fn_items)
    if note_refs:
        body = _substitute_note_markers(body, note_refs, href_by_note or {})
    if note_items:
        body += "\n" + _render_notes_section(note_items)
    return body


def _page(title: str, body: str, *, lang: str) -> str:
    """组装一页完整 XHTML 文档（恰好一个 h1 位于 body 首行由调用方保证）。

    ``<title>`` 必须走 ``plain_label()``：单元 md 的 h1 常带 pandoc 行内属性
    （``# Dedication {#calibre_toc_2}``），直接 ``escape(title)`` 会把
    ``{#calibre_toc_2}`` 原样写进 ``<title>``，读者在阅读器标签页/书目里看到
    字面属性块（实测 Thiriart 22 处、fierce-enigmas 17 处）。
    该属性块在 h1 上仍由 ``_split_heading_id`` 正常提取为 id，**不受影响**
    ——目录链接依赖那些 id，故此处只清理 ``<title>`` 的可见文本。
    与 nav 标签同用 ``plain_label``，避免两处口径不一致。
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" '
        f'xml:lang="{escape(lang, quote=True)}" '
        f'lang="{escape(lang, quote=True)}">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        '<link rel="stylesheet" type="text/css" href="style.css"/>\n'
        f"<title>{escape(plain_label(title))}</title>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def subheading_anchors(md: str, unit_id: str) -> list[dict[str, Any]]:
    """扫描单元 md 的 level≥2 子标题，返回 nav 锚点清单（纯函数）。

    块遍历语义与 ``markdown_to_xhtml`` 逐字一致（按空行切块、块首行匹配、
    ``{#id}`` 剥离、level≥2 计数含显式 id 者）——保证此处返回的 ``anchor``
    与渲染产物中的 ``id`` 一一对应，nav 链接不悬空。
    返回 ``[{"level": 2..6, "title": str, "anchor": str}]``（文档顺序）。
    """
    anchors: list[dict[str, Any]] = []
    n = 0
    for block in _iter_blocks(md):
        block = block.strip("\n")
        if not block.strip():
            continue
        lines = block.splitlines()
        m = _HEADING_RE.match(lines[0])
        if not m:
            continue
        level = min(len(m.group(1)), 6)
        if level < 2:
            continue
        n += 1
        title, hid = _split_heading_id(m.group(2))
        title = plain_label(title)
        if title:
            anchors.append({"level": level, "title": title, "anchor": hid or f"{unit_id}-h{n}"})
    return anchors


def render_document(
    title: str,
    md_text: str,
    *,
    lang: str,
    unit_id: str = "",
    fn_state: FootnoteState | None = None,
    note_refs: dict[str, NoteRef] | None = None,
    note_items: list[NoteItem] | None = None,
    href_by_note: dict[str, str] | None = None,
) -> str:
    """渲染一页纯译文文档（md_text 为结构化单元 markdown）。

    ``unit_id`` + ``fn_state`` 提供时启用旧记法脚注语义化；``note_refs`` /
    ``note_items`` 提供时启用 N 阶段结构化注释（epub-template-spec §6）。
    """
    body = markdown_to_xhtml(
        md_text,
        unit_id=unit_id,
        fn_state=fn_state,
        note_refs=note_refs,
        note_items=note_items,
        href_by_note=href_by_note,
    )
    return _page(title, body, lang=lang)


def slug_file(unit_id: str) -> str:
    """把稳定单元 ID 转成安全的文件名 slug（保留字母数字/连字符/下划线）。"""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", unit_id).strip("-")
    return slug or "unit"
