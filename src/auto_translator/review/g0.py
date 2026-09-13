"""G0 零 token 静态校验（纯函数，翻译后立即、离线、确定性）。

输入来自 ``translation/align/<id>.jsonl``、``structured/<id>.md`` 与 ``analysis/glossary.csv``。
G0 不烧 token、不出"裁决"，只出确定性告警，作为 G1 的输入线索。

**接线状态**：``g0_unit_flags``（import 与 g0 命令的唯一入口）当前执行五类检查——
align（对照表完整性）/ length（长度比，advisory）/ terminology（术语命中）/
marker（插入标记守恒）/ footnote（脚注标记守恒，含 pandoc 与数字式两种表示）。
本模块其余函数（标题层级、段落块、断字符修复、排印讹误、
标点规范化）是历史实践提炼的纯函数工具，供 agent 审校时人工比对使用，
尚未接入自动校验（后续扩展点）。

历史实践提炼（docs/quality-lessons.md + 旧真实案例）：
- 插入元素标记数量守恒（``{fig:NNN}`` 32/32）；
- 注码/脚注引用守恒（1:1）；
- h1/h2 层级数量与源文一致；
- 段落块数量 1:1（允许页断残句合并的合理差异）；
- 断字符修复（IsraelEgypt→Israel-Egypt、BenGurion→Ben-Gurion、19491955→1949-1955）；
- 排印讹误按先例修正（IDG→IDF、19487→1948）；
- 标点规范化（«»→《》、""→「」、...→…）；
- 术语命中（glossary source 出现时译文须含 target）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..glossary import Glossary, terminology_hits

# 插入元素标记，如 {fig:NNN}、{table:NNN}
_MARKER_RE = re.compile(r"\{\w+:\d+\}")

# 近似脚注注码：**句末**标点后紧跟 1~3 位数字（排除小数如 3.14）。
# 只认句末标点（. ! ? … 。 ！ ？）；引证里的冒号/分号/逗号（如 1992:110、「；1 公顷」）
# 不是注码，否则会把统计数字误判为脚注标记而触发守恒硬缺陷。
_FOOTNOTE_REF_RE = re.compile(r"(?<!\d)[.!?…。！？](\d{1,3})(?!\d)")

# pandoc 脚注标记：[^label] 引用与 [^label]: 定义 统一计数
_FN_PANDOC_RE = re.compile(r"\[\^[^\]\s]+\]")

_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)

# 常见排印讹误先例（源文勘误，来自旧真实案例）
_DEFAULT_CORRECTIONS: dict[str, str] = {
    "IDG": "IDF",
    "19487": "1948",
    "67 December": "6-7 December",
}

# OUP 等版权残句特征（构建/审校时统一剔除）
_COPYRIGHT_MARKERS = (
    "All rights reserved",
    "First published",
    "Printed in",
    "Library of Congress Cataloging",
    "British Library Cataloguing",
)


@dataclass(frozen=True)
class G0Flag:
    """一条确定性告警。"""

    check: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


def count_markers(text: str, pattern: re.Pattern[str] = _MARKER_RE) -> int:
    """统计插入元素标记（{fig:NNN} 等）数量。"""
    return len(pattern.findall(text or ""))


def markers_conserved(src: str, tgt: str, pattern: re.Pattern[str] = _MARKER_RE) -> bool:
    """标记数量守恒：源与译的标记数一致。"""
    return count_markers(src, pattern) == count_markers(tgt, pattern)


def count_footnote_refs(text: str) -> int:
    """统计句末注码（脚注引用）数量（PDF 文字层数字式注码）。"""
    return len(_FOOTNOTE_REF_RE.findall(text or ""))


def count_footnote_marks(text: str) -> int:
    """统计 pandoc 脚注标记（[^label] 引用与定义）数量。"""
    return len(_FN_PANDOC_RE.findall(text or ""))


def count_heading_levels(text: str) -> dict[int, int]:
    """统计各标题层级（h1~h6）数量。"""
    levels: dict[int, int] = {}
    for m in _HEADING_RE.finditer(text or ""):
        level = len(m.group(1))
        levels[level] = levels.get(level, 0) + 1
    return levels


def count_paragraph_blocks(text: str) -> int:
    """统计段落块数量（按空行分隔）。"""
    parts = re.split(r"\n\s*\n", (text or "").strip("\n"))
    return len([p for p in parts if p.strip()])


# ── 交付审计（S1.1）：translation md ↔ align tgt 全文一致性 ────────────────

# 标题行（h1/h2：build 的 h1 来自 publication title，不在 align 行内）
_HEADING_LINE = re.compile(r"(?m)^\s*#{1,6}\s+.*$")
# 脚注定义前缀（[^label]:）
_FN_DEF_PREFIX = re.compile(r"\[\^[^\]]+\]:")


def _drift_norm(text: str) -> str:
    """漂移比对归一化：去标题行/脚注定义前缀/脚注与插入标记，再去全部空白。"""
    out = _HEADING_LINE.sub("", text or "")
    out = _FN_DEF_PREFIX.sub("", out)
    out = _FN_PANDOC_RE.sub("", out)
    out = _MARKER_RE.sub("", out)
    return re.sub(r"\s+", "", out)


def _strip_def_blocks(text: str) -> str:
    """整段剔除脚注定义块（定义行 + 其非空续行）——align 不含定义行时的容错模式。"""
    out: list[str] = []
    in_def = False
    for line in (text or "").splitlines():
        if _FN_DEF_PREFIX.match(line.lstrip()):
            in_def = True
            continue
        if in_def:
            if line.strip():
                continue  # 定义续行
            in_def = False
        out.append(line)
    return "\n".join(out)


def md_align_drift(
    md_text: str, rows: list[dict[str, Any]], *, title: str | None = None
) -> list[str]:
    """translation md ↔ align tgt 全文一致性（交付审计 S1.1，纯函数）。

    ``translation/<rel>.md`` 是 build 的输入，``align/<id>.jsonl`` 是 import 校验的
    基准，二者由同一翻译动作产生：归一化（去标题行/脚注定义/标记/空白）后应完全
    一致。不一致 = 一侧缺内容——真实案例：md 丢 38 处图片引用段与部分脚注，align
    完整，工具守恒（align 级）全过，缺陷直达成品。

    容错：``title`` 非空时剔除与单元标题对应的一条 align 行（align 常含标题行，
    而 md 的标题由 build 从单元 title 渲染）；align 不含脚注定义行时，md 侧定义块
    整段忽略（「align 只收句级正文」的约定）；align 含定义行时严格比对定义文本。

    返回差异摘要列表（空列表 = 一致）。只描述「哪侧缺内容」，不改文本。
    """
    ordered = sorted(rows, key=lambda r: int(r.get("seq") or 0))
    if title:
        tn = _drift_norm(title)
        if tn:
            for idx, r in enumerate(ordered):
                if tn in (
                    _drift_norm(str(r.get("tgt") or "")),
                    _drift_norm(str(r.get("src") or "")),
                ):
                    ordered.pop(idx)
                    break
    align_has_defs = any(_FN_DEF_PREFIX.match(str(r.get("tgt") or "").lstrip()) for r in ordered)
    md_input = md_text if align_has_defs else _strip_def_blocks(md_text)
    md_norm = _drift_norm(md_input)
    tgt_norm = _drift_norm("".join(str(r.get("tgt") or "") for r in ordered))
    if md_norm == tgt_norm:
        return []
    missing_in_md = [
        str(r.get("seq"))
        for r in ordered
        if _drift_norm(str(r.get("tgt") or ""))
        and _drift_norm(str(r.get("tgt") or "")) not in md_norm
    ]
    md_blocks = [
        b.strip()
        for b in re.split(r"\n\s*\n", (md_input or "").strip("\n"))
        if b.strip() and not b.strip().startswith("#")
    ]
    missing_in_align = [
        b[:40] for b in md_blocks if _drift_norm(b) and _drift_norm(b) not in tgt_norm
    ]
    parts = [
        f"translation md 与 align tgt 不一致（md {len(md_norm)} 字符 / align {len(tgt_norm)} 字符）"
    ]
    if missing_in_md:
        parts.append(
            f"align 有而 md 缺 {len(missing_in_md)} 处（seq={','.join(missing_in_md[:8])}）"
        )
    if missing_in_align:
        parts.append(
            f"md 有而 align 缺 {len(missing_in_align)} 处（{'；'.join(missing_in_align[:3])}）"
        )
    if not missing_in_md and not missing_in_align:
        parts.append("差异为顺序或重复（非缺内容），请以 align 为准核对")
    return ["；".join(parts)]


def length_ratio(src: str, tgt: str) -> float:
    """译文/源文长度比；空源文返回 0。"""
    s = len((src or "").strip())
    if s == 0:
        return 0.0
    return len((tgt or "").strip()) / s


def repair_missing_hyphens(text: str) -> str:
    """修复缺失的连字符/连接号（IsraelEgypt→Israel-Egypt、19491955→1949-1955 等）。

    规则：两个字母之间、或相邻两段 4 位年份之间缺连字符时补上。
    """
    out = text or ""
    # 字母-字母：IsraelEgypt / BenGurion
    out = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", "-", out)
    # 年份粘连：19491955 → 1949-1955
    out = re.sub(r"(?<=\d{4})(?=\d{4})", "-", out)
    return out


def apply_corrections(text: str, corrections: dict[str, str] | None = None) -> str:
    """按先例修正排印讹误（IDG→IDF 等），返回 (修正后文本, 命中的修正项)。"""
    mapping = {**(_DEFAULT_CORRECTIONS if corrections is None else corrections)}
    out = text or ""
    for wrong, right in mapping.items():
        out = out.replace(wrong, right)
    return out


def detect_corrections(
    text: str, corrections: dict[str, str] | None = None
) -> list[tuple[str, str]]:
    """检测文本命中的已知排印讹误（源文勘误线索；纯函数，不改文本）。"""
    mapping = {**(_DEFAULT_CORRECTIONS if corrections is None else corrections)}
    return [(wrong, right) for wrong, right in mapping.items() if wrong in (text or "")]


def annotate_correction_notes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按句 src 命中的勘误先例给 align 行补 note 前缀（``corr:wrong→right``）。

    留痕源错修正：溯源时区分「译错」与「源错按先例修正」。不改 src/tgt 文本。
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        hits = detect_corrections(row.get("src") or "")
        if hits:
            prefix = "corr:" + ",".join(f"{w}→{r}" for w, r in hits)
            note = row.get("note")
            row = {**row, "note": f"{prefix};{note}" if note else prefix}
        out.append(row)
    return out


def strip_copyright_boilerplate(lines: list[str]) -> list[str]:
    """剔除版权残句（从含版权特征的连续块开始截断到末尾）。"""
    text = "\n".join(lines)
    for marker in _COPYRIGHT_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            # 截断自该版权块起始行
            head = text[:idx].rstrip("\n")
            return head.split("\n") if head else []
    return lines


def normalize_punctuation(text: str, lang: str = "zh-CN") -> str:
    """标点规范化：«»→《》、""→「」、...→…（纯函数，目标语言为中文时）。"""
    t = (text or "").replace("«", "《").replace("»", "》").replace("...", "…")
    if lang not in ("zh-CN", "zh-TW", "ja"):
        return t
    out: list[str] = []
    open_stack: list[str] = []
    for ch in t:
        if ch == '"':
            if open_stack:
                out.append(open_stack.pop())
            else:
                open_stack.append("」")
                out.append("「")
        else:
            out.append(ch)
    while open_stack:
        out.append(open_stack.pop())
    return "".join(out)


def check_alignment(rows: list[dict[str, Any]]) -> list[G0Flag]:
    """对照表完整性：seq 连续 1..N 无缺号无重复、每行 src/tgt 非空。"""
    flags: list[G0Flag] = []
    seqs = [r.get("seq") for r in rows]
    if not seqs:
        flags.append(G0Flag("align", "对照表为空"))
        return flags
    if seqs != list(range(1, len(rows) + 1)):
        flags.append(G0Flag("align", "seq 不连续", {"seqs": seqs}))
    empty_src = [r["seq"] for r in rows if not (r.get("src") or "").strip()]
    empty_tgt = [r["seq"] for r in rows if not (r.get("tgt") or "").strip()]
    if empty_src:
        flags.append(G0Flag("align", "存在空原文", {"seq": empty_src}))
    if empty_tgt:
        flags.append(G0Flag("align", "存在空译文", {"seq": empty_tgt}))
    return flags


def g0_unit_flags(
    rows: list[dict[str, Any]],
    glossary: Glossary,
    *,
    too_short: float = 0.30,
    too_long: float = 3.0,
    structured_md: str | None = None,
) -> list[G0Flag]:
    """对一个单元执行全部 G0 检查，返回告警列表。

    检查项：align（对照表完整性）/ length（长度比，advisory）/ terminology（术语
    命中）/ marker（插入标记守恒）/ footnote（脚注标记守恒）。守恒类做**单元级
    总量比对**而非行级——拆句/并句会把标记挪到相邻行，总量守恒恰好对应
    「一个都不能丢」且不误报。

    ``structured_md`` 非空时追加**源保真（fidelity）双向检查**（见 fidelity.py）：
    前向缺块=advisory、反向 src 失配=硬缺陷（import 阻断）。
    """
    flags = list(check_alignment(rows))
    sum_marker_src = sum_marker_tgt = 0
    sum_fn_src = sum_fn_tgt = 0
    for r in rows:
        src = r.get("src") or ""
        tgt = r.get("tgt") or ""
        seq = r.get("seq")
        ratio = length_ratio(src, tgt)
        if not tgt.strip():
            flags.append(G0Flag("length", "译文为空", {"seq": seq}))
        elif ratio < too_short:
            flags.append(G0Flag("length", "长度比过低（疑漏译）", {"seq": seq, "ratio": ratio}))
        elif ratio > too_long:
            flags.append(G0Flag("length", "长度比过高（疑失控）", {"seq": seq, "ratio": ratio}))
        for hit in terminology_hits(src, tgt, glossary):
            flags.append(
                G0Flag(
                    "terminology",
                    f"术语 {hit.source} 译文缺失 {hit.expected}",
                    {"seq": seq, "source": hit.source, "expected": hit.expected},
                )
            )
        sum_marker_src += count_markers(src)
        sum_marker_tgt += count_markers(tgt)
        sum_fn_src += count_footnote_refs(src) + count_footnote_marks(src)
        sum_fn_tgt += count_footnote_refs(tgt) + count_footnote_marks(tgt)
    if sum_marker_src != sum_marker_tgt:
        flags.append(
            G0Flag(
                "marker",
                "插入标记数量不守恒",
                {"src": sum_marker_src, "tgt": sum_marker_tgt},
            )
        )
    if sum_fn_src != sum_fn_tgt:
        flags.append(
            G0Flag(
                "footnote",
                "脚注标记数量不守恒",
                {"src": sum_fn_src, "tgt": sum_fn_tgt},
            )
        )
    if structured_md is not None:
        from .fidelity import fidelity_flags

        flags.extend(fidelity_flags(structured_md, rows))
    return flags


# ── 表格形状守恒（S4.2；学 epub-builder table.Validate 的不变量，不学其交换格式）──

# md 分隔行：| --- | :---: | ...
_SEP_LINE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")

# 非转义管道符（\| 是字面竖线，不计列）
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _count_cols(line: str) -> int:
    """统计一行表格的列数（剥首尾 | 后按非转义 | 切分）。"""
    body = (line or "").strip().strip("|")
    if not body:
        return 0
    return len(_UNESCAPED_PIPE.split(body))


def parse_md_tables(md: str) -> list[dict[str, int]]:
    """解析 md 管道表格 → ``[{"rows": R, "cols": C}]``（按出现顺序）。

    表 = ≥2 个连续「含 | 的非空行」且第 2 行是分隔行；行数含表头与分隔行；
    跳过 ``` 围栏内的行；转义管道 ``\\|`` 不计列。
    """
    tables: list[dict[str, int]] = []
    lines = (md or "").splitlines()
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if not in_fence and "|" in line:
            block: list[str] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                block.append(lines[i])
                i += 1
            if len(block) >= 2 and _SEP_LINE.match(block[1]):
                tables.append({"rows": len(block), "cols": _count_cols(block[0])})
            continue
        i += 1
    return tables


def table_shape_flags(src_md: str, tgt_md: str) -> list[G0Flag]:
    """表格形状守恒：表数一致、逐表 rows/cols 一致；差异即硬缺陷级 flag。"""
    flags: list[G0Flag] = []
    src_tables = parse_md_tables(src_md)
    tgt_tables = parse_md_tables(tgt_md)
    if len(src_tables) != len(tgt_tables):
        flags.append(
            G0Flag(
                "table",
                "表格数量不守恒",
                {"src": len(src_tables), "tgt": len(tgt_tables)},
            )
        )
        return flags
    for i, (s, t) in enumerate(zip(src_tables, tgt_tables, strict=False), start=1):
        if s != t:
            flags.append(
                G0Flag(
                    "table",
                    "表格形状不守恒",
                    {
                        "index": i,
                        "src": f"{s['rows']}x{s['cols']}",
                        "tgt": f"{t['rows']}x{t['cols']}",
                    },
                )
            )
    return flags
