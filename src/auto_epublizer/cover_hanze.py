# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""「汉译学术本」封面版式（issue #100）：纸纹 + 双线框 + 四段式文字 + 意象区。

来源：issue #100 的三本书实测规格（1600×2400 画布），本模块把像素坐标换算成
页宽 W / 页高 H 的比例，因此换开本不会散架。

与 quarto 不同的地方：

1. **有底纹**：纸色 + 细噪声 + 低频斑块 + 边缘晕影（纯 Python 生成一张小图放大，
   不引入 numpy/PIL）。
2. **有框**：外框（主色 3px）+ 内框（金 1px）+ 四角短线。
3. **四段式**：丛书行 / 中文书名 + 副题 / 英文原题 + 副题 / 编者行，全部居中。
4. **有意象区**：``motif`` 取 ``globe``（经纬网地球）或 ``arch``（尖拱窗），
   也可以留空只出框与字。

**可辨认底线**（与 quarto 共用）：600px 宽的成品上最小字号必须 ≥14px，
即 ``MIN_TYPE_FRAC``；issue 里 27–34px 的小字在 600px 下只有 10–13px，
这里按底线统一提到 2.34% 页宽——版式骨架不动，只把小字提亮到读得清。
"""

from __future__ import annotations

import functools
import math
import random

import pymupdf

from .cover import (
    INK,
    MIN_TYPE_FRAC,
    CoverSpec,
    Fonts,
    _hex,
    _is_cjk,
    _Measurer,
    wrap,
)

#: 纸色 / 金 / 墨 / 次级墨（issue #100 的三本书取色的公共部分）。
PAPER = "#F0E7D4"
GOLD = "#A38248"
INK_C = "#22201C"
MUTED = "#6A6252"  # 丛书行、书系签、出版行
FAINT = "#7E6E58"  # 免责行
ORIG = "#4A4E3C"  # 英文原题
ORIG_SUB = "#5E5242"  # 英文副题
VIGNETTE = "#746448"  # 边缘晕影的棕

#: 主色预设（三本已交付书 + 通用几档）；``--accent`` 可直接覆盖。
ACCENTS: dict[str, str] = {
    "ochre": "#7A2222",  # 赭红（全球马克思）
    "forest": "#1A3E2C",  # 深绿（马克思主义与中世纪研究）
    "moss": "#1B3428",  # 墨绿（俄国关税政策）
    "ink": "#22201C",
    "navy": "#1F3350",
    "plum": "#5B2140",
}

#: 意象种类。
MOTIFS = ("none", "globe", "arch")

#: issue #100 的设计画布（版面坐标就用这套像素值，再整体缩放到页面）。
DESIGN_W = 1600
DESIGN_H = 2400

#: 版式比例（issue #100 的 1600×2400 画布 → 页宽/页高比例）。
GEOM = {
    "outer": (0.03625, 0.02417, 0.97375, 0.97583),
    "inner": (0.04500, 0.03000, 0.96500, 0.97000),
    "outer_w": 0.00190,  # 3px/1600
    "inner_w": 0.00063,  # 1px/1600
    "tick": 0.02875,  # 四角短线 46px
    "tick_w": 0.00125,  # 2px
    "series_y": 0.0625,  # 150/2400
    "rule1_y": 0.0875,  # 210
    "rule1_half": 0.1875,  # 300/1600
    "title_y": 0.125,  # 300
    "sub_y": 0.1875,  # 450
    "orig_y": 0.2450,
    "origsub_y": 0.2720,
    "credits_y": 0.3850,
    "motif_top": 0.4170,
    "motif_bottom": 0.6880,
    "rule2_y": 0.7290,  # 1750
    "rule2_half": 0.20625,  # 330/1600
    "sign_y": 0.7500,  # 1800
    "mark_y": 0.7900,  # 1896
    "pub_y": 0.8420,  # 2020
    "note_y": 0.8670,  # 2080
    "rule_dot": 0.0075,  # 中央圆点半径 12px
}

#: 字号（设计画布 px；渲染时按 scale 缩放，并夹到 MIN_TYPE_FRAC 之上）。
#: issue 的 27–34px 小字在 600px 宽下只有 10–13px，按可辨认底线统一提到 14px 等效。
TYPE = {
    "series": 30,  # issue 27–30
    "title_max": 168,
    "title_min": 96,
    "subtitle": 60,
    "original": 55,
    "original_sub": 40,
    "credits": 42,
    "signature": 68,
    "mark": 40,
    "publisher": 34,
    "note": 30,
}

#: 字距（设计画布 px）。
TRACK = {
    "series": 5,
    "title": 10,
    "subtitle": 6,
    "original": 3,
    "original_sub": 1,
    "credits": 2,
    "signature": 10,
    "mark": 6,
    "publisher": 8,
    "note": 2,
}

#: 行高（× 字号）。
LEADING = {"original_sub": 1.35, "credits": 1.55}


def effective_type(key: str, width: float, height: float) -> float:
    """某一段文字在给定页面上的**实际**字号（设计值缩放后不小于可辨认底线）。

    版式按 1600×2400 设计画布排；换开本时整体等比缩放，小字再由
    ``MIN_TYPE_FRAC`` 抬到「600px 宽下 14px」的等效大小。
    """
    scale = min(width / DESIGN_W, height / DESIGN_H)
    return max(TYPE[key] * scale, MIN_TYPE_FRAC * width)


def fit_title(
    text: str, inner_w: float, width: float, height: float, measurer: _Measurer
) -> tuple[float, list[str]]:
    """书名自适应：168→96 设计像素之间收字号，仍超宽才折行（issue #100 的要求）。"""
    scale = min(width / DESIGN_W, height / DESIGN_H)
    track = TRACK["title"] * scale
    size = TYPE["title_max"] * scale
    while (
        size > TYPE["title_min"] * scale and _tracked_width(measurer, text, size, track) > inner_w
    ):
        size *= 0.97
    size = max(size, max(TYPE["title_min"] * scale, MIN_TYPE_FRAC * width))
    return size, (wrap(text, inner_w, size, measurer) or [text])


# ---------------------------------------------------------------- 纸底
def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


@functools.lru_cache(maxsize=4)
def _paper_pixmap(
    paper: str = PAPER, seed: int = 7, width: int = 400, height: int = 600
) -> pymupdf.Pixmap:
    """纸底：底色 + 细噪声 + 低频斑块 + 边缘晕影（确定性，小图放大当纹理用）。"""
    rnd = random.Random(seed)
    base = _hex(paper)
    vign = _hex(VIGNETTE)

    # 低频斑块：16×24 网格双线性插值（对应 issue 的「1/8 尺度污渍」）
    gw, gh = 16, 24
    grid = [[rnd.gauss(0.0, 0.012) for _ in range(gw)] for _ in range(gh)]

    def mottle(u: float, v: float) -> float:
        gx, gy = u * (gw - 1), v * (gh - 1)
        x0, y0 = int(gx), int(gy)
        x1, y1 = min(x0 + 1, gw - 1), min(y0 + 1, gh - 1)
        fx, fy = gx - x0, gy - y0
        top = grid[y0][x0] * (1 - fx) + grid[y0][x1] * fx
        bottom = grid[y1][x0] * (1 - fx) + grid[y1][x1] * fx
        return top * (1 - fy) + bottom * fy

    buf = bytearray(width * height * 3)
    band = 0.16  # 晕影从边缘向内衰减的宽度（占短边比例）
    for y in range(height):
        v = y / (height - 1)
        dy = min(v, 1 - v) / band
        for x in range(width):
            u = x / (width - 1)
            dx = min(u, 1 - u) / band
            dark = 1.0 - _smoothstep(min(dx, dy))  # 0=中心, 1=边缘
            shade = dark * 0.55
            grain = rnd.gauss(0.0, 0.004)
            m = mottle(u, v) + grain
            i = (y * width + x) * 3
            for c in range(3):
                val = base[c] * (1 - shade) + vign[c] * shade + m
                buf[i + c] = max(0, min(255, int(val * 255 + 0.5)))
    return pymupdf.Pixmap(pymupdf.csRGB, width, height, bytes(buf), False)


# ---------------------------------------------------------------- 工具
def _tracked_width(measurer: _Measurer, text: str, size: float, tracking: float) -> float:
    total = (
        sum(f.text_length(ch, fontsize=size) for ch, f in _chars(measurer, text)) if text else 0.0
    )
    return total + tracking * max(len(text) - 1, 0)


def _chars(measurer: _Measurer, text: str):
    """逐字给出 (字符, 字体)：CJK 用中文字体，其余用拉丁字体。"""
    for ch in text:
        yield ch, (measurer.cjk if _is_cjk(ch) else measurer.latin)


def _emit(
    writers: dict[tuple, pymupdf.TextWriter],
    page: pymupdf.Rect,
    measurer: _Measurer,
    text: str,
    size: float,
    cx: float,
    baseline: float,
    color: tuple[float, float, float],
    tracking: float = 0.0,
) -> None:
    """居中画一行（逐字控制字距）。"""
    width = _tracked_width(measurer, text, size, tracking)
    x = cx - width / 2
    key = tuple(round(c, 6) for c in color)
    tw = writers.get(key)
    if tw is None:
        tw = writers[key] = pymupdf.TextWriter(page)
    for ch, font in _chars(measurer, text):
        tw.append((x, baseline), ch, font=font, fontsize=size)
        x += font.text_length(ch, fontsize=size) + tracking


def _rule(
    page: pymupdf.Page,
    cx: float,
    y: float,
    half: float,
    color: tuple,
    width: float,
    dot: float = 0.0,
) -> None:
    page.draw_line(
        pymupdf.Point(cx - half, y), pymupdf.Point(cx + half, y), color=color, width=width
    )
    if dot:
        page.draw_circle(pymupdf.Point(cx, y), dot, color=None, fill=color, width=0)


# ---------------------------------------------------------------- 意象
def _motif_globe(page: pymupdf.Page, cx: float, cy: float, r: float, accent: tuple) -> None:
    """经纬网地球 + 环绕航线 + 节点（issue 里《全球马克思》的意象）。"""
    faint = (accent[0], accent[1], accent[2])
    page.draw_circle(pymupdf.Point(cx, cy), r, color=faint, width=1.1)
    # 经线：15/30/45/60/75 度 → 半宽 r·cos
    for deg in (75, 60, 45, 30, 15):
        rx = r * math.cos(math.radians(deg))
        page.draw_oval(pymupdf.Rect(cx - rx, cy - r, cx + rx, cy + r), color=faint, width=0.5)
    page.draw_oval(pymupdf.Rect(cx - r, cy - r, cx + r, cy + r), color=faint, width=1.1)
    # 纬线：±15…±75 度，弦长 2r·cos
    for deg in (15, 30, 45, 60, 75):
        half = r * math.cos(math.radians(deg))
        yy = cy - r * math.sin(math.radians(deg))
        page.draw_line(
            pymupdf.Point(cx - half, yy), pymupdf.Point(cx + half, yy), color=faint, width=0.5
        )
        page.draw_line(
            pymupdf.Point(cx - half, 2 * cy - yy),
            pymupdf.Point(cx + half, 2 * cy - yy),
            color=faint,
            width=0.5,
        )
    page.draw_line(pymupdf.Point(cx - r, cy), pymupdf.Point(cx + r, cy), color=faint, width=1.6)
    # 航线：两条外扩椭圆弧（用折线近似，避免旋转 API）
    for ax, ay, a0, a1 in ((1.22, 1.08, 200, 340), (1.10, 1.20, 20, 150)):
        pts = []
        steps = 40
        for i in range(steps + 1):
            ang = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append(pymupdf.Point(cx + r * ax * math.cos(ang), cy + r * ay * math.sin(ang)))
        page.draw_polyline(pts, color=faint, width=0.6)
    # 六个节点
    for deg in (25, 90, 155, 210, 290, 335):
        ang = math.radians(deg)
        page.draw_circle(
            pymupdf.Point(cx + r * 1.16 * math.cos(ang), cy + r * 1.16 * math.sin(ang)),
            r * 0.018,
            color=None,
            fill=faint,
            width=0,
        )


def _motif_arch(
    page: pymupdf.Page,
    cx: float,
    top: float,
    bottom: float,
    width: float,
    accent: tuple,
    faint: tuple,
) -> None:
    """等边尖拱窗 + 三分窗棂 + 拱顶三叶饰 + 抄本横格（issue 里《中世纪研究》的意象）。

    ``top``/``bottom`` 是意象区上下沿（已缩放到页面坐标）。拱为**等边尖拱**：
    两段半径 = 拱宽的圆弧在拱顶相交，夹角 60°，因此拱顶是真正的尖角而不是圆头。
    横格按 46 设计像素间距叠加，只铺在拱内——读起来像一页摊开的手抄本。
    """
    w = min(width, (bottom - top) / 1.22)
    head = w * math.sqrt(3) / 2  # 0.866w：等边尖拱的拱高
    jamb = w * 0.26  # 拱肩以下的下墙
    spring = top + (bottom - top - head - jamb) / 2 + head
    base = spring + jamb
    half = w / 2
    left, right = cx - half, cx + half
    apex = spring - head

    def arc(center_x: float, start_deg: float, end_deg: float) -> None:
        pts = []
        steps = 48
        for i in range(steps + 1):
            ang = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            pts.append(pymupdf.Point(center_x + w * math.cos(ang), spring + w * math.sin(ang)))
        page.draw_polyline(pts, color=accent, width=1.3)

    arc(right, 180, 240)  # 右心圆：左起拱点 → 拱顶
    arc(left, 300, 360)  # 左心圆：拱顶 → 右起拱点
    page.draw_line(
        pymupdf.Point(left, spring), pymupdf.Point(right, spring), color=accent, width=1.3
    )
    page.draw_line(pymupdf.Point(left, spring), pymupdf.Point(left, base), color=accent, width=1.3)
    page.draw_line(
        pymupdf.Point(right, spring), pymupdf.Point(right, base), color=accent, width=1.3
    )
    page.draw_line(pymupdf.Point(left, base), pymupdf.Point(right, base), color=accent, width=1.3)

    # 抄本横格：拱内按弦长裁切（间距 46 设计像素），拱尖端留白
    step = w * 0.092
    y = spring - step * 0.55
    while y > apex + step * 1.6:
        chord = math.sqrt(max(w * w - (spring - y) ** 2, 0.0)) - half
        if chord > w * 0.05:
            page.draw_line(
                pymupdf.Point(cx - chord, y), pymupdf.Point(cx + chord, y), color=faint, width=0.45
            )
        y -= step
    # 下墙：三条横格铺满（不分棂，避免栅栏感）
    for i in (1, 2, 3):
        y = spring + jamb * i / 4
        page.draw_line(pymupdf.Point(left, y), pymupdf.Point(right, y), color=faint, width=0.45)

    # 三分窗棂：两根石柱把窗分成三椟
    for x in (cx - w / 6, cx + w / 6):
        page.draw_line(pymupdf.Point(x, spring), pymupdf.Point(x, base), color=accent, width=0.9)

    # 拱顶三叶饰：外圈 + 三瓣，贴着拱尖下方
    r_ring = w * 0.072
    ring_y = apex + r_ring * 2.2
    page.draw_circle(pymupdf.Point(cx, ring_y), r_ring, color=accent, width=0.8)
    lobe = r_ring * 0.52
    for deg in (90, 210, 330):
        ang = math.radians(deg)
        page.draw_circle(
            pymupdf.Point(
                cx + r_ring * 0.30 * math.cos(ang), ring_y - r_ring * 0.30 * math.sin(ang)
            ),
            lobe,
            color=accent,
            width=0.7,
        )


# ---------------------------------------------------------------- 版面
def draw(spec: CoverSpec, fonts: Fonts) -> pymupdf.Document:
    """渲染「汉译学术本」封面。

    版面按 issue #100 的 **1600×2400 设计画布**排（坐标就是规格里的像素值），
    再整体等比缩放居中到页面上：换开本时版式不变形，只是纸边留白略多。
    """
    W, H = spec.width, spec.height
    scale = min(W / DESIGN_W, H / DESIGN_H)
    ox = (W - DESIGN_W * scale) / 2
    oy = (H - DESIGN_H * scale) / 2

    def X(px: float) -> float:
        return ox + px * scale

    def Y(px: float) -> float:
        return oy + px * scale

    def S(px: float) -> float:
        return px * scale

    m = _Measurer(fonts)
    colors = spec.colors
    paper, gold, accent = colors["paper"], colors["gold"], colors["accent"]
    ink, muted, faint = colors["ink"], colors["muted"], colors["faint"]
    orig_c, origsub_c = colors["orig"], colors["orig_sub"]

    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.insert_image(page.rect, pixmap=_paper_pixmap(paper))

    # 双线框 + 四角短线
    ox0, oy0, ox1, oy1 = (X(58), Y(58), X(1558), Y(2342))
    ix0, iy0, ix1, iy1 = (X(72), Y(72), X(1544), Y(2328))
    page.draw_rect(pymupdf.Rect(ox0, oy0, ox1, oy1), color=_hex(accent), width=max(S(3), 0.8))
    page.draw_rect(pymupdf.Rect(ix0, iy0, ix1, iy1), color=_hex(gold), width=max(S(1), 0.35))
    tick = S(46)
    gold_rgb = _hex(gold)
    for px, py, dx, dy in (
        (ix0, iy0, 1, 1),
        (ix1, iy0, -1, 1),
        (ix0, iy1, 1, -1),
        (ix1, iy1, -1, -1),
    ):
        page.draw_line(
            pymupdf.Point(px, py),
            pymupdf.Point(px + dx * tick, py),
            color=gold_rgb,
            width=max(S(2), 0.5),
        )
        page.draw_line(
            pymupdf.Point(px, py),
            pymupdf.Point(px, py + dy * tick),
            color=gold_rgb,
            width=max(S(2), 0.5),
        )

    cx = W / 2
    writers: dict[tuple, pymupdf.TextWriter] = {}

    def baseline_at(px: float) -> float:
        return Y(px)

    def emit(text: str, size: float, y_px: float, color: str, key: str) -> None:
        size = max(size, MIN_TYPE_FRAC * W)
        _emit(writers, page.rect, m, text, size, cx, baseline_at(y_px), _hex(color), S(TRACK[key]))

    # 丛书行（英文小字）
    if spec.series:
        emit(spec.series[0], effective_type("series", W, H), 150, muted, "series")

    # 分隔线（金 + 中央圆点）
    _rule(page, cx, Y(205), S(300), gold_rgb, max(S(1.4), 0.6), dot=S(4))

    # 中文书名：168→96px 自适应，按「墨迹顶 = 250」摆；超宽折行时后续各段跟着下移
    title_text = "".join(spec.title)
    inner_w = S(1544 - 72 - 80)
    title_size, title_lines = fit_title(title_text, inner_w, W, H, m)
    title_top = Y(250)
    baseline = title_top + INK["cjk"][0] * title_size
    for i, text in enumerate(title_lines):
        if i:
            baseline += 1.18 * title_size
        _emit(
            writers, page.rect, m, text, title_size, cx, baseline, _hex(accent), S(TRACK["title"])
        )
    prev_bottom = baseline + INK["cjk"][1] * title_size

    def place(design_y: float, size: float, top_ratio: float, bottom_ratio: float, gap: float):
        """按设计位置摆一行；若上一块压下来，则顺延（保证不叠字）。"""
        nonlocal prev_bottom
        y = max(Y(design_y), prev_bottom + gap)
        base = y + top_ratio * size
        prev_bottom = base + bottom_ratio * size
        return base

    # 副题
    for text in spec.subtitle:
        size = effective_type("subtitle", W, H)
        base = place(500, size, INK["cjk"][0], INK["cjk"][1], 0.10 * size)
        _emit(writers, page.rect, m, text, size, cx, base, _hex(ink), S(TRACK["subtitle"]))

    # 英文原题
    for text in spec.original_title[:1]:
        size = effective_type("original", W, H)
        base = place(620, size, INK["latin"][0], INK["latin"][1], 0.06 * size)
        _emit(writers, page.rect, m, text, size, cx, base, _hex(orig_c), S(TRACK["original"]))

    # 英文副题（最多两行）
    for i, text in enumerate(spec.original_subtitle[:2]):
        size = effective_type("original_sub", W, H)
        base = place(680 + i * 54, size, INK["latin"][0], INK["latin"][1], 0.05 * size)
        _emit(
            writers, page.rect, m, text, size, cx, base, _hex(origsub_c), S(TRACK["original_sub"])
        )

    # 编者 / 责任者行
    for i, text in enumerate(spec.credits):
        size = effective_type("credits", W, H)
        base = place(930 + i * 66, size, INK["cjk"][0], INK["cjk"][1], 0.06 * size)
        _emit(writers, page.rect, m, text, size, cx, base, _hex(ink), S(TRACK["credits"]))

    # 意象区
    if spec.motif in ("globe", "arch"):
        accent_rgb = _hex(accent)
        if spec.motif == "globe":
            _motif_globe(page, cx, Y((1000 + 1650) / 2), S(236), accent_rgb)
        else:
            _motif_arch(page, cx, Y(1000), Y(1650), S(520), accent_rgb, _hex(faint))

    # 底线
    _rule(page, cx, Y(1720), S(330), gold_rgb, max(S(1.4), 0.6))

    # 署名：配置里的署名 + 角色（默认「译」）
    if spec.imprint:
        role = spec.credit_role
        text = f"{spec.imprint}　{role}" if role else spec.imprint
        emit(text, effective_type("signature", W, H), 1800, ink, "signature")

    if spec.series_mark:
        emit(spec.series_mark, effective_type("mark", W, H), 1896, muted, "mark")
    if spec.publisher_line:
        emit(spec.publisher_line, effective_type("publisher", W, H), 2020, muted, "publisher")
    if spec.note_line:
        emit(spec.note_line, effective_type("note", W, H), 2080, faint, "note")

    for color, tw in writers.items():
        tw.write_text(page, color=color)
    return doc
