"""RTL（从右向左）文本抽取支持：检测、归一化、行内逻辑序还原。

PDF 中的 RTL 文本（波斯语/阿拉伯语/希伯来语等）常用**呈现形字符**
（U+FB50–FDFF、U+FE70–FEFF）编码，并混入**双向控制符**（U+202A–202E、U+2066–2069、
LRM/RLM）。PyMuPDF 按**视觉 x 从左到右**输出 span/line，对 RTL 即为**逻辑倒序**：
``شهزاده. آوردند قتل به ...`` 实为 ``... به قتل آوردند. شهزاده``。

本模块提供确定性纯函数。只在判定为 RTL 的**书**上启用重排与归一化，
LTR 文本字节级不变（见 ``read_pdf`` 的 ``rtl`` 参数）。仅用标准库 ``unicodedata``。

算法与验证：对同一页，本模块「按行 token 逆序」的结果与 poppler ``pdftotext``
（完整实现 UAX#9）在本书上达到 ~0.96 的词序一致率（残差来自行/段切分差异，
非顺序错误）。**不做括号镜像**：实测抽取器已输出逻辑形括号码点，镜像反而会破坏。
"""

from __future__ import annotations

import unicodedata

# 强方向性字符（参与方向统计）
_STRONG_RTL = frozenset({"R", "AL"})
_STRONG_LTR = frozenset({"L"})

# 需要剥离的方向控制/标记：LRM/RLM、LRE/RLE/PDF/LRO/RLO、LRI/RLI/FSI/PDI、ALM。
# 注意保留 ZWNJ(U+200C)/ZWJ(U+200D)——波斯语用 ZWNJ 构词，不能删。
_BIDI_CONTROLS = frozenset(
    {
        0x061C,  # ARABIC LETTER MARK
        0x200E,  # LEFT-TO-RIGHT MARK
        0x200F,  # RIGHT-TO-LEFT MARK
        0x202A,  # LEFT-TO-RIGHT EMBEDDING
        0x202B,  # RIGHT-TO-LEFT EMBEDDING
        0x202C,  # POP DIRECTIONAL FORMATTING
        0x202D,  # LEFT-TO-RIGHT OVERRIDE
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0x2067,  # RIGHT-TO-LEFT ISOLATE
        0x2068,  # FIRST STRONG ISOLATE
        0x2069,  # POP DIRECTIONAL ISOLATE
    }
)

# 判定一本书/一行是否 RTL 的强方向性占比阈值
RTL_THRESHOLD = 0.5


def _count_direction(text: str) -> tuple[int, int]:
    """返回 (强 RTL 字符数, 强 LTR 字符数)，跳过方向控制符与中性字符。"""
    rtl = ltr = 0
    for ch in text:
        if ord(ch) in _BIDI_CONTROLS:
            continue
        bidi = unicodedata.bidirectional(ch)
        if bidi in _STRONG_RTL:
            rtl += 1
        elif bidi in _STRONG_LTR:
            ltr += 1
    return rtl, ltr


def rtl_ratio(text: str) -> float:
    """强方向性字符中 RTL 的占比；无强方向性字符时返回 0.0。"""
    rtl, ltr = _count_direction(text)
    total = rtl + ltr
    return rtl / total if total else 0.0


def is_rtl_text(text: str, *, threshold: float = RTL_THRESHOLD) -> bool:
    """单行/单段是否以 RTL 为主（保护 RTL 书中夹杂的拉丁引文与数字行）。"""
    return rtl_ratio(text) >= threshold


def detect_book_rtl(
    texts: list[str] | tuple[str, ...], *, threshold: float = RTL_THRESHOLD
) -> bool:
    """书级判定：汇总全部文本的强方向性字符计数（比逐段平均更稳）。"""
    rtl = ltr = 0
    for text in texts:
        n_rtl, n_ltr = _count_direction(text)
        rtl += n_rtl
        ltr += n_ltr
    total = rtl + ltr
    return (rtl / total if total else 0.0) >= threshold


def strip_bidi_controls(text: str) -> str:
    """剥离双向控制/标记字符（保留 ZWNJ/ZWJ）。"""
    return "".join(ch for ch in text if ord(ch) not in _BIDI_CONTROLS)


def normalize_rtl(text: str) -> str:
    """RTL 文本归一化：先剥方向控制符，再做 NFKC（呈现形 → 基础字母）。"""
    return unicodedata.normalize("NFKC", strip_bidi_controls(text))


def reorder_line(text: str) -> str:
    """把一行视觉序（x 从左到右）还原为逻辑序：空格 token 整体逆序。

    token 逆序天然保留 token 内部的拉丁词/数字串顺序；跨行断词留待下游。
    空白与单个 token 原样返回。
    """
    tokens = text.split()
    if len(tokens) < 2:
        return text
    return " ".join(reversed(tokens))


def normalize_and_reorder(text: str, *, threshold: float = RTL_THRESHOLD) -> str:
    """RTL 书内单行处理：归一化后，仅对 RTL 为主的行做 token 逆序。"""
    normalized = normalize_rtl(text)
    if is_rtl_text(normalized, threshold=threshold):
        return reorder_line(normalized)
    return normalized
