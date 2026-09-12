"""EPUB 内部链接 / 锚点重写：把 pandoc 产出的源文件引用映射到成品单元文件。

背景
----
``pandoc -f epub`` 把整本 EPUB 转 Markdown 时，会给内部引用加上源文件名前缀：

- 内部链接 ``<a href="ch17.html#page_311">`` → ``[311](#ch17.html#page_311)``
  （注意 pandoc 额外加的前导 ``#``，形成两个 ``#`` 的非法 URI，epubcheck
  RSC-020/RSC-005）；
- 空锚点 ``<a id="page_311">`` → ``[]{#ch17.html#page_311}``（可能带 class）；
- 标题锚点 ``<h2 id="ch17">`` → ``## 标题 {#ch17.html#ch17 .h1}``。

这三类都引用**源文件名**，而成品按 OPF spine 重新切分、以单元 id 命名
（``ch19.xhtml``），二者存在整体偏移；不重写则跳转目标不存在（RSC-012），
锚点若被直接删除则索引里上千个链接失去落点。

本模块在 ``classify_units``（已分配最终单元 id）之后、``write_structured`` 之前
运行，依据每个单元的 ``meta.spine_href``（源 href）建立「源文件 → 单元」映射，
把链接、空锚点、标题 id 统一确定性改写为成品形态：

- 跨单元链接 ``[x](#ch17.html#p)`` → ``[x](ch19.xhtml#p)``；
- 同单元引用 ``[]{#ch17.html#p}`` / ``{#ch17.html#ch17 .h1}`` → ``[]{#p}`` /
  ``{#ch17}``（去文件前缀与 class）。

外部链接（http/mailto 等）与无法映射的目标保持原样，不做猜测。
"""

from __future__ import annotations

import posixpath
import re

# markdown 行内链接：[label](target)，target 可能被 < > 包裹
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(\s*<?([^)>]*?)>?\s*\)")
# 空锚点 span：[]{#id} 或 []{#id .class1 .class2}（class 丢弃）
_ANCHOR_SPAN_RE = re.compile(r"\[\]\{#([^}\s]+)(?:\s+[^}]*)?\}")
# 元素属性块：{#id} 或 {#id .class ...}（标题 id，class 丢弃）
_ATTR_BLOCK_RE = re.compile(r"\{#([^}\s]+)(?:\s+[^}]*)?\}")
# 外部协议链接（不重写）
_EXTERNAL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def _src_basename(spine_href: str) -> str:
    """``Text/ch17.html`` → ``ch17``（去目录与扩展名）。"""
    base = posixpath.basename((spine_href or "").split("#", 1)[0])
    return base.rsplit(".", 1)[0] if "." in base else base


def build_src_to_unit(classified) -> dict[str, str]:
    """从已归类单元构建 {源文件 basename: 单元 id} 映射。"""
    mapping: dict[str, str] = {}
    for cls in classified:
        href = (cls.unit.meta or {}).get("spine_href", "")
        name = _src_basename(href)
        if name:
            mapping.setdefault(name, cls.unit_id)
    return mapping


def _rewrite_target(target: str, current_unit: str, src_map: dict[str, str]) -> str | None:
    """把单个引用目标改写为成品内部目标；外部/无法映射时返回 None（保留原样）。

    返回值形态：``#fragment``（同单元纯锚点）或 ``<unit>.xhtml[#fragment]``（跨单元）。
    """
    raw = (target or "").strip()
    if not raw:
        return None
    # pandoc -f epub 给内部链接加的前导 #（#ch17.html#page_311）
    if raw.startswith("#"):
        raw = raw[1:]
    if not raw or _EXTERNAL_RE.match(raw):
        return None
    path, sep, fragment = raw.partition("#")
    base = posixpath.basename(path)
    if "." not in base:
        # path 无扩展名：整体就是同文件锚点（page_21 / ch02），不是源文件引用
        anchor = fragment if sep else path
        return f"#{anchor}" if anchor else None
    name = _src_basename(path)
    target_unit = src_map.get(name)
    if target_unit is None:
        return None  # 源文件不在 spine 映射中（非线性项/外部），保留原样
    if target_unit == current_unit:
        return f"#{fragment}" if fragment else f"{target_unit}.xhtml"
    return f"{target_unit}.xhtml#{fragment}" if fragment else f"{target_unit}.xhtml"


def rewrite_links_in_text(text: str, current_unit: str, src_map: dict[str, str]) -> str:
    """改写一段 markdown 文本中的内部链接、空锚点与标题 id（确定性纯函数）。"""

    def _link(m: re.Match[str]) -> str:
        label, target = m.group(1), m.group(2).strip()
        new_target = _rewrite_target(target, current_unit, src_map)
        if new_target is None or new_target == target:
            return m.group(0)
        return f"[{label}]({new_target})"

    def _anchor(m: re.Match[str]) -> str:
        # 空锚点是「目标定义」，落点就在当前单元：只保留 # 之后的纯锚点 id
        new_target = _rewrite_target(m.group(1), current_unit, src_map)
        if new_target is None:
            return m.group(0)
        frag = new_target.rsplit("#", 1)[-1]
        return f"[]{{#{frag}}}" if frag else m.group(0)

    def _attr(m: re.Match[str]) -> str:
        new_target = _rewrite_target(m.group(1), current_unit, src_map)
        if new_target is None:
            return m.group(0)
        frag = new_target.rsplit("#", 1)[-1]
        return f"{{#{frag}}}" if frag else m.group(0)

    text = _MD_LINK_RE.sub(_link, text)
    text = _ANCHOR_SPAN_RE.sub(_anchor, text)
    text = _ATTR_BLOCK_RE.sub(_attr, text)
    return text


def rewrite_internal_links(doc, classified) -> int:
    """就地重写 ``doc`` 全部单元段落中的内部链接/锚点，返回改写处数。"""
    src_map = build_src_to_unit(classified)
    total = 0
    for cls in classified:
        for seg in cls.unit.segments:
            if not seg.source:
                continue
            if not any(tok in seg.source for tok in ("](" , "{#")):
                continue
            new_source = rewrite_links_in_text(seg.source, cls.unit_id, src_map)
            if new_source != seg.source:
                total += 1
                seg.source = new_source
    return total
