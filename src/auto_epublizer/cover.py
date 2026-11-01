# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""生成式书封（Magadan 版式）：metadata + 设计稿 → 确定性 PNG/PDF。

为什么需要：译作常常没有可用的封面——扫描件首页图未必是封面（issue #63 已规定
「未确认不当封面」），纯文本/Markdown 源根本没有封面图，成品因此在书架与锁屏上
空白。本模块给这类书一套**统一的排版封面**：白底 + 顶部通栏色带 + 右侧竖色条 +
右对齐宋体书名群 + 底部行书署名。

三条硬约束：

1. **零 token**：版式是纯排版参数（比例、字号、色值），没有任何模型调用；文字来自
   ``publication.json`` 元数据与 agent 手写的 ``preprocessing/cover-spec.json``。
2. **不猜语义**：没有副书名就是没有副书名。本模块只把已存在的字段摆到版式里，
   绝不从 description 里切句子充当副书名。
3. **不抢源封面**：源书确认过的封面（``preprocessing/cover.json``）优先；生成封面只在
   没有源封面时使用。生成件登记在 ``preprocessing/cover-generated.json``，与源封面
   互不覆盖。

版式比例全部实测自参考样张（1500×2120 基准，换算为页宽 W / 页高 H 的比例），
见 ``GEOM``/``TYPE``/``GAPS``；改这些常数等于改版式，改动后请重跑
``tests/test_cover_render.py`` 的对版断言。

字体：中文思源宋体、拉丁 Nimbus Roman/Times、行书署名用志莽行书一类手写体；
全部按系统字体发现，找不到时降级并**明说**（不静默换字体而假装是同一套封面）。
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from auto_common.workspace import RunStore

#: 设计稿（agent 手写，可选）：副书名/原文名/署名行/配色等元数据装不下的内容。
SPEC_FILE = "preprocessing/cover-spec.json"
#: 生成封面登记（CLI 写）：文件 + 摘要 + 设计摘要，用于构建期同步与过期判定。
RECORD_FILE = "preprocessing/cover-generated.json"
#: 生成封面的落盘位置（与其它媒体同目录，build 直接按 EPUB 相对路径引用）。
GENERATED_REL = "structured/raw/media/cover-generated.png"

#: 色板：主色（通栏色带）与侧条色（可与主色不同，如蓝带 + 金边）。实测自样张。
PALETTES: dict[str, tuple[str, str]] = {
    "indigo": ("#0D1168", "#0D1168"),
    "blue": ("#2C5F9E", "#FECB00"),
    "maroon": ("#612326", "#612326"),
    "purple": ("#4B2C65", "#4B2C65"),
    "crimson": ("#962311", "#962311"),
    "brown": ("#5A2B1B", "#5A2B1B"),
    "green": ("#236243", "#236243"),
    "ink": ("#1A1A1A", "#1A1A1A"),
}

#: 版式（页宽 W / 页高 H 的比例）。来源：参考样张逐像素实测。
GEOM = {
    "band_top": 0.0135,
    "band_h": 0.0528,
    "bar_left": 0.897,
    "bar_w": 0.021,
    "content_right": 0.882,
    "content_left": 0.080,
    "block_ink_top": 0.3099,
    "series_left": 0.030,
    "series_ink_top": 0.084,
    "imprint_center": 0.470,
    "imprint_ink_top": 0.9191,
}

#: 字号（/ 页宽）。
TYPE = {
    "title": 0.0767,
    "subtitle": 0.0375,
    "original_title": 0.0383,
    "original_subtitle": 0.0295,
    "credits": 0.0294,
    "lead": 0.0295,
    "series": 0.0300,
    "imprint": 0.0330,
}

#: 行高（× 字号）。
LINE_HEIGHT = {
    "title": 1.02,
    "subtitle": 1.12,
    "original_title": 1.15,
    "original_subtitle": 1.15,
    "credits": 1.50,
    "lead": 1.25,
}

#: 块间距（/ 页高，墨迹到墨迹）：实测自样张，保住「书名群」的呼吸感。
GAPS = {
    "lead_title": 0.0120,
    "title_subtitle": 0.0224,
    "subtitle_original": 0.0262,
    "original_originalsub": 0.0120,
    "originalsub_credits": 0.0235,
}

#: 墨迹相对基线的比例（上, 下）：CJK 全角字 / 拉丁衬线 / 行书。实测（见模块文档）。
INK = {
    "cjk": (0.84, 0.07),
    "latin": (0.68, 0.21),
    "script": (0.80, 0.00),
}

#: 不能出现在行首的标点（中文断行规则）；命中则强行并入上一行。
NO_LINE_START = "。，、；：？！）》」』】〕…—·%‰’”"

#: 行书署名字体候选（先找文件，再退 fc-match）。
SCRIPT_FONTS = (
    "ZhiMangXing-Regular",
    "MaShanZheng-Regular",
    "LongCang-Regular",
    "LiuJianMaoCao-Regular",
    "STXingkai",
    "华文行楷",
    "LXGWWenKai-Regular",
)
CJK_FONTS = (
    "NotoSerifCJK-Regular",
    "NotoSerifCJKsc-Regular",
    "SourceHanSerifSC-Regular",
    "SourceHanSerif-Regular",
    "Songti",
    "STSong",
    "simsun",
)
LATIN_FONTS = (
    "NimbusRoman-Regular",
    "Times New Roman",
    "Times",
    "LiberationSerif-Regular",
    "DejaVuSerif",
)
FONT_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.local/share/fonts",
    "~/.fonts",
    "/System/Library/Fonts",
    "/Library/Fonts",
    "C:/Windows/Fonts",
)


class CoverError(ValueError):
    """封面设计稿/字体不可用（用户可预期的输入或环境问题）。"""


@dataclass(frozen=True)
class Fonts:
    """渲染所需字体文件；``missing`` 记录降级项，供命令明确告知。"""

    cjk: Path
    latin: Path | None
    script: Path | None
    missing: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        return {
            "cjk": self.cjk.name,
            "latin": self.latin.name if self.latin else None,
            "script": self.script.name if self.script else None,
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class CoverSpec:
    """一份可渲染的封面设计（已解析、已换行切分、已算好字号）。"""

    width: float
    height: float
    background: str
    ink: str
    band: str
    bar: str
    title: list[str]
    subtitle: list[str] = field(default_factory=list)
    original_title: list[str] = field(default_factory=list)
    original_subtitle: list[str] = field(default_factory=list)
    credits: list[str] = field(default_factory=list)
    lead: list[str] = field(default_factory=list)
    series: list[str] = field(default_factory=list)
    imprint: str = ""
    style: str = "magadan"
    palette: str = "indigo"

    def digest(self) -> str:
        """设计摘要：内容一变，构建期就能发现封面过期。"""
        payload = {
            "style": self.style,
            "palette": self.palette,
            "size": [round(self.width, 3), round(self.height, 3)],
            "colors": [self.band, self.bar, self.ink, self.background],
            "texts": [
                self.title,
                self.subtitle,
                self.original_title,
                self.original_subtitle,
                self.credits,
                self.lead,
                self.series,
                self.imprint,
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 字体发现
def _expand_dirs(dirs: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for raw in dirs:
        path = Path(os.path.expanduser(raw))
        if path.is_dir():
            out.append(path)
    return out


@functools.lru_cache(maxsize=4)
def _walk_fonts_cached(dirs: tuple[Path, ...]) -> tuple[Path, ...]:
    found: list[Path] = []
    for root in dirs:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower().endswith((".ttf", ".otf", ".ttc", ".otc")):
                    found.append(Path(dirpath) / name)
    return tuple(found)


def _walk_fonts(dirs: Sequence[Path]) -> tuple[Path, ...]:
    """递归收集字体文件（只取常见后缀）；结果按目录集合缓存（构建期会反复取字体）。"""
    return _walk_fonts_cached(tuple(dirs))


def _match_by_name(files: Sequence[Path], needles: Sequence[str]) -> Path | None:
    """按文件名子串匹配（大小写不敏感）；.otf/.ttf 优先于 .ttc（带面索引的老字体）。"""
    ranked: list[tuple[int, int, Path]] = []
    for path in files:
        stem = path.stem.lower()
        # 变体（Bold/Italic）与「SC/JP/KR 语言面」都不适合做正文基准
        if any(bad in stem for bad in ("bold", "italic", "oblique", "heavy", "black")):
            continue
        for rank, needle in enumerate(needles):
            if needle.lower() in stem:
                ext_rank = 0 if path.suffix.lower() in (".otf", ".ttf") else 1
                ranked.append((rank, ext_rank, path))
                break
    ranked.sort(key=lambda item: (item[0], item[1], str(item[2])))
    return ranked[0][2] if ranked else None


def _fc_match(family: str) -> Path | None:
    """fontconfig 兜底（Linux/BSD），返回的文件必须**真属于**该家族。

    ``fc-match`` 对不存在的家族也会给出「最相近」结果，不核对就会把 DejaVu Sans
    当成行书/宋体用——中文直接变豆腐块，还装作没事。
    """
    exe = shutil.which("fc-match")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-f", "%{file}\n%{family}", family],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    first, _, families = out.stdout.partition("\n")
    path = Path(first.strip())
    if not path.is_file():
        return None
    wanted = family.replace(" ", "").lower()
    actual = families.replace(" ", "").lower()
    return path if wanted in actual else None


def find_fonts(*, cjk: str = "", latin: str = "", script: str = "") -> Fonts:
    """定位 CJK / 拉丁 / 行书字体；显式路径优先，其次系统目录，最后 fontconfig。"""
    files: Sequence[Path] | None = None
    dirs = _expand_dirs(FONT_DIRS)

    def _collect() -> Sequence[Path]:
        nonlocal files
        if files is None:
            files = _walk_fonts(dirs)
        return files

    missing: list[str] = []

    def _pick(explicit: str, needles: Sequence[str], families: Sequence[str]) -> Path | None:
        if explicit:
            path = Path(os.path.expanduser(explicit))
            if not path.is_file():
                raise CoverError(f"字体文件不存在：{explicit}")
            return path
        found = _match_by_name(_collect(), needles)
        if found is not None:
            return found
        for family in families:
            match = _fc_match(family)
            if match is not None:
                return match
        return None

    cjk_path = _pick(
        cjk, CJK_FONTS, ("Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", "SimSun")
    )
    if cjk_path is None:
        raise CoverError(
            "找不到中文字体（思源宋体/Noto Serif CJK）；"
            "安装 fonts-noto-cjk 或在配置 cover.font_serif 指定 .otf/.ttf"
        )
    latin_path = _pick(latin, LATIN_FONTS, ("Nimbus Roman", "Times New Roman", "Liberation Serif"))
    if latin_path is None:
        missing.append("latin")
    script_path = _pick(
        script, SCRIPT_FONTS, ("Zhi Mang Xing", "Ma Shan Zheng", "STXingkai", "华文行楷")
    )
    if script_path is None:
        missing.append("script")
    return Fonts(cjk=cjk_path, latin=latin_path, script=script_path, missing=tuple(missing))


# ---------------------------------------------------------------- 设计稿
def read_spec_file(store: RunStore | None) -> dict[str, Any]:
    """读 ``preprocessing/cover-spec.json``（agent 手写设计稿）；不合格 → ValueError。"""
    if store is None:
        return {}
    path = store.dir / SPEC_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverError(f"{SPEC_FILE} 不可读：{exc}") from None
    if not isinstance(payload, dict):
        raise CoverError(f"{SPEC_FILE} 必须是 JSON 对象")
    allowed = {
        "style",
        "palette",
        "title",
        "subtitle",
        "original_title",
        "original_subtitle",
        "credits",
        "lead",
        "series",
        "imprint",
        "size",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CoverError(f"{SPEC_FILE} 含未知字段：{'、'.join(unknown)}")
    for key in (
        "title",
        "subtitle",
        "original_title",
        "original_subtitle",
        "imprint",
        "lead",
        "series",
        "style",
        "palette",
        "size",
    ):
        if key in payload and payload[key] is not None and not isinstance(payload[key], str):
            raise CoverError(f"{SPEC_FILE} 的 {key} 必须是字符串")
    if "credits" in payload:
        credits = payload["credits"]
        if isinstance(credits, str):
            payload["credits"] = [credits]
        elif not (isinstance(credits, list) and all(isinstance(c, str) for c in credits)):
            raise CoverError(f"{SPEC_FILE} 的 credits 必须是字符串数组")
    return payload


def _lines(text: str) -> list[str]:
    """按显式换行切分，丢掉空行（版式里空行没有意义，只会撑开间距）。"""
    return [line.strip() for line in str(text).replace("\r\n", "\n").split("\n") if line.strip()]


def _flatten(entries: Iterable[str]) -> list[str]:
    """一行一个责任者；条目内允许显式换行。"""
    out: list[str] = []
    for entry in entries:
        out.extend(_lines(entry))
    return out


def _default_credits(meta: Any) -> list[str]:
    """没有设计稿时的责任者行：只摆已知事实，不编国籍/不猜角色。"""
    lines: list[str] = []
    if meta.creator:
        lines.append(f"{meta.creator} 著")
    if meta.translator:
        lines.append(f"{meta.translator} 译")
    return lines


def resolve_spec(
    pub: Any,
    cfg: Any,
    *,
    spec_file: dict[str, Any] | None = None,
    palette: str | None = None,
    imprint: str | None = None,
    size: str | None = None,
) -> CoverSpec:
    """元数据 + 设计稿 + 命令行覆盖 → CoverSpec（不渲染、不落盘）。"""
    from auto_epublizer.pdfexport import SIZES

    overrides = spec_file or {}
    meta = pub.meta

    title_text = str(overrides.get("title") or meta.title_translated or meta.title or "").strip()
    if not title_text:
        raise CoverError(
            "没有书名，无法生成封面；先 meta --title 或写 preprocessing/cover-spec.json"
        )

    # 原文书名：只有与展示书名不同才作为「原文名」出现，避免同一行重复两遍
    original = overrides.get("original_title")
    if original is None:
        source_title = str(meta.title or "").strip()
        original = source_title if source_title and source_title != title_text else ""

    palette_name = str(palette or overrides.get("palette") or cfg.cover.palette or "indigo")
    if palette_name not in PALETTES:
        raise CoverError(f"未知色板：{palette_name}（可选 {', '.join(PALETTES)}）")
    band, bar = PALETTES[palette_name]

    size_name = str(size or overrides.get("size") or cfg.cover.size or "a5").lower()
    if size_name not in SIZES:
        raise CoverError(f"未知开本：{size_name}（可选 {', '.join(SIZES)}）")
    mm_w, mm_h = SIZES[size_name]
    width = mm_w * 72 / 25.4
    height = mm_h * 72 / 25.4

    imprint_text = (
        imprint if imprint is not None else (overrides.get("imprint") or cfg.cover.imprint or "")
    )

    return CoverSpec(
        width=width,
        height=height,
        background="#FFFFFF",
        ink="#000000",
        band=band,
        bar=bar,
        title=_lines(title_text),
        subtitle=_lines(overrides.get("subtitle") or ""),
        original_title=_lines(original or ""),
        original_subtitle=_lines(overrides.get("original_subtitle") or ""),
        credits=_flatten(overrides.get("credits") or _default_credits(meta)),
        lead=_lines(overrides.get("lead") or ""),
        series=_lines(overrides.get("series") or ""),
        imprint=str(imprint_text).strip(),
        style=str(overrides.get("style") or cfg.cover.style or "magadan"),
        palette=palette_name,
    )


# ---------------------------------------------------------------- 排版
def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3000 <= code <= 0x30FF  # CJK 标点 / 假名
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0xFF00 <= code <= 0xFFEF  # 全角
        or 0x2E80 <= code <= 0x2EFF
    )


def _tokenize(text: str) -> list[str]:
    """CJK 逐字成词（中文可任意断行），拉丁整词成词，空白黏在前一词尾。"""
    tokens: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            tokens.append("".join(buf))
            buf.clear()

    for ch in text:
        if _is_cjk(ch):
            flush()
            tokens.append(ch)
        elif ch.isspace():
            flush()
            if tokens:
                tokens[-1] += " "
        else:
            buf.append(ch)
    flush()
    return tokens


class _Measurer:
    """按字符脚本选字体并量宽（同一次渲染内缓存 Font 对象）。"""

    def __init__(self, fonts: Fonts) -> None:
        self._cjk = pymupdf.Font(fontfile=str(fonts.cjk))
        self._latin = pymupdf.Font(fontfile=str(fonts.latin)) if fonts.latin else self._cjk
        self._script = pymupdf.Font(fontfile=str(fonts.script)) if fonts.script else self._cjk

    @property
    def cjk(self) -> pymupdf.Font:
        return self._cjk

    @property
    def latin(self) -> pymupdf.Font:
        return self._latin

    @property
    def script(self) -> pymupdf.Font:
        return self._script

    def runs(self, text: str, *, script: bool = False) -> list[tuple[str, pymupdf.Font]]:
        """把一行切成「同字体连续段」，保留拉丁整词以避免字距被拆开。"""
        if script:
            return [(text, self._script)]
        runs: list[tuple[str, pymupdf.Font]] = []
        for chunk in _tokenize(text):
            font = self._cjk if all(_is_cjk(c) or c == " " for c in chunk) else self._latin
            if runs and runs[-1][1] is font:
                runs[-1] = (runs[-1][0] + chunk, font)
            else:
                runs.append((chunk, font))
        return runs

    def width(self, text: str, size: float, *, script: bool = False) -> float:
        total = 0.0
        for chunk, font in self.runs(text, script=script):
            total += font.text_length(chunk, fontsize=size)
        return total


def wrap(
    text: str, width: float, size: float, measurer: _Measurer, *, script: bool = False
) -> list[str]:
    """按版心宽度断行，并在行数不变的前提下把各行长度摊平（balance）。"""
    tokens = _tokenize(text) if not script else [text]
    if not tokens:
        return []

    def layout(limit: float) -> list[str]:
        lines: list[list[str]] = [[]]
        used = 0.0
        for token in tokens:
            token_w = measurer.width(token, size)
            if token == " " and not lines[-1]:
                continue  # 行首空格丢弃
            # 行首禁则：标点黏在上一行，宁可轻微超宽
            if token in NO_LINE_START and lines[-1] and used + token_w > limit:
                lines[-1].append(token)
                used += token_w
                continue
            if lines[-1] and used + token_w > limit:
                lines.append([token])
                used = token_w
            else:
                lines[-1].append(token)
                used += token_w
        return ["".join(line).rstrip() for line in lines if "".join(line).strip()]

    natural = layout(width)
    if len(natural) <= 1:
        return natural
    total = max(measurer.width(line, size) for line in natural)
    # 用「总宽/n」做上界二分，找仍能保持 n 行的最窄版心 → 各行等长
    low, high = total / len(natural), width
    best = natural
    for _ in range(18):
        mid = (low + high) / 2
        candidate = layout(mid)
        if len(candidate) <= len(natural):
            best = candidate
            high = mid
        else:
            low = mid
    return best


def _fit_title(lines: list[str], measurer: _Measurer, base: float, content_w: float) -> float:
    """书名超宽时整体缩小，最多缩到 62%（再长交给断行）。"""
    if not lines:
        return base
    widest = max(measurer.width(line, base) for line in lines)
    if widest <= content_w:
        return base
    return max(base * content_w / widest * 0.97, base * 0.62)


# ---------------------------------------------------------------- 渲染
def _hex(color: str) -> tuple[float, float, float]:
    """``#RRGGBB`` → RGB 三元组（**不能**给 4 元组：MuPDF 会当成 CMYK，白会变黑）。"""
    value = color.lstrip("#")
    if len(value) != 6:
        raise CoverError(f"色值格式不对：{color}（应为 #RRGGBB）")
    try:
        return (
            int(value[0:2], 16) / 255,
            int(value[2:4], 16) / 255,
            int(value[4:6], 16) / 255,
        )
    except ValueError:
        raise CoverError(f"色值格式不对：{color}（应为 #RRGGBB）") from None


def _draw(spec: CoverSpec, fonts: Fonts) -> pymupdf.Document:
    """把设计画到一页上（纯排版，无外部进程）。"""
    measurer = _Measurer(fonts)
    width, height = spec.width, spec.height
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.draw_rect(
        pymupdf.Rect(0, 0, width, height), color=None, fill=_hex(spec.background), width=0
    )

    # 顶部通栏色带 + 右侧竖色条（色条自色带下沿到页底，右侧留白由 bar_left/bar_w 决定）
    band_top = GEOM["band_top"] * height
    band_h = GEOM["band_h"] * height
    page.draw_rect(
        pymupdf.Rect(0, band_top, width, band_top + band_h),
        color=None,
        fill=_hex(spec.band),
        width=0,
    )
    bar_left = GEOM["bar_left"] * width
    bar_w = GEOM["bar_w"] * width
    page.draw_rect(
        pymupdf.Rect(bar_left, band_top, bar_left + bar_w, height),
        color=None,
        fill=_hex(spec.bar),
        width=0,
    )

    content_right = GEOM["content_right"] * width
    content_w = content_right - GEOM["content_left"] * width
    ink = _hex(spec.ink)
    tw = pymupdf.TextWriter(page.rect)

    def emit(
        lines: list[str],
        size: float,
        *,
        right: float | None = None,
        left: float | None = None,
        baseline: float,
        script: bool = False,
    ) -> None:
        for line in lines:
            text_w = measurer.width(line, size, script=script)
            x = (right - text_w) if right is not None else (left or 0.0)
            for chunk, font in measurer.runs(line, script=script):
                tw.append((x, baseline), chunk, font=font, fontsize=size)
                x += font.text_length(chunk, fontsize=size)

    def advance(size: float, key: str) -> float:
        return LINE_HEIGHT[key] * size

    # —— 左上丛书名 ——
    if spec.series:
        size = TYPE["series"] * width
        baseline = GEOM["series_ink_top"] * height + INK["cjk"][0] * size
        emit(spec.series, size, left=GEOM["series_left"] * width, baseline=baseline)

    # —— 书名群（右对齐，自上而下）——
    y = GEOM["block_ink_top"] * height

    def block(lines: list[str], key: str, size: float, *, gap_after: float) -> None:
        nonlocal y
        if not lines:
            return
        top_ratio = (
            INK["cjk"][0] if any(_is_cjk(c) for line in lines for c in line) else INK["latin"][0]
        )
        baseline = y + top_ratio * size
        for index, line in enumerate(lines):
            if index:
                baseline += advance(size, key)
            emit([line], size, right=content_right, baseline=baseline)
        bottom_ratio = (
            INK["cjk"][1] if any(_is_cjk(c) for line in lines for c in line) else INK["latin"][1]
        )
        y = baseline + bottom_ratio * size + gap_after * height

    if spec.lead:
        size = TYPE["lead"] * width
        block(spec.lead, "lead", size, gap_after=GAPS["lead_title"])

    if spec.title:
        size = (
            _fit_title(spec.title, measurer, TYPE["title"] * width, content_w) if spec.title else 0
        )
        # 超宽书名再按版心断行（标题保持最小 62% 前提下的自然折行）
        title_lines: list[str] = []
        for line in spec.title:
            if measurer.width(line, size) > content_w:
                title_lines.extend(wrap(line, content_w, size, measurer) or [line])
            else:
                title_lines.append(line)
        block(title_lines, "title", size, gap_after=GAPS["title_subtitle"])

    if spec.subtitle:
        size = TYPE["subtitle"] * width
        lines = [
            w for line in spec.subtitle for w in (wrap(line, content_w, size, measurer) or [line])
        ]
        block(lines, "subtitle", size, gap_after=GAPS["subtitle_original"])

    if spec.original_title:
        size = TYPE["original_title"] * width
        lines = [
            w
            for line in spec.original_title
            for w in (wrap(line, content_w, size, measurer) or [line])
        ]
        block(lines, "original_title", size, gap_after=GAPS["original_originalsub"])

    if spec.original_subtitle:
        size = TYPE["original_subtitle"] * width
        lines = [
            w
            for line in spec.original_subtitle
            for w in (wrap(line, content_w, size, measurer) or [line])
        ]
        block(lines, "original_subtitle", size, gap_after=GAPS["originalsub_credits"])

    if spec.credits:
        size = TYPE["credits"] * width
        lines = [
            w for line in spec.credits for w in (wrap(line, content_w, size, measurer) or [line])
        ]
        block(lines, "credits", size, gap_after=0.0)

    # —— 底部署名（行书；无行书字体时降级为宋体并明示）——
    if spec.imprint:
        size = TYPE["imprint"] * width
        text_w = measurer.width(spec.imprint, size, script=fonts.script is not None)
        baseline = GEOM["imprint_ink_top"] * height + INK["script"][0] * size
        x = GEOM["imprint_center"] * width - text_w / 2
        if fonts.script is None:
            # 降级：宋体 + 字距，保住「署名居中靠底」的版式，但不再是行书
            tracking = 0.004 * width
            for chunk, font in measurer.runs(spec.imprint):
                tw.append((x, baseline), chunk, font=font, fontsize=size)
                x += font.text_length(chunk, fontsize=size) + tracking
        else:
            # 行书单字笔画偏细：按 0.012em 叠画三次补一点点笔重（等同 faux bold，
            # 但仍是矢量文字，不描边、不模糊）
            shift = 0.012 * size
            for dx, dy in ((0.0, 0.0), (shift, 0.0), (0.0, shift)):
                tw.append(
                    (x + dx, baseline + dy), spec.imprint, font=measurer.script, fontsize=size
                )

    tw.write_text(page, color=ink)
    return doc


def render_png(spec: CoverSpec, fonts: Fonts, *, dpi: int = 300) -> bytes:
    """渲染为 PNG 字节（确定性：同输入同输出）。"""
    if dpi < 72 or dpi > 1200:
        raise CoverError(f"dpi 超出范围（72–1200）：{dpi}")
    doc = _draw(spec, fonts)
    try:
        pixmap = doc[0].get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")
    finally:
        doc.close()


def render_pdf(spec: CoverSpec, fonts: Fonts) -> bytes:
    """渲染为单页 PDF 字节（与 PNG 同一版面，便于印刷核对）。"""
    doc = _draw(spec, fonts)
    try:
        doc.set_metadata({"title": " ".join(spec.title), "producer": "auto-epublizer"})
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()


# ---------------------------------------------------------------- 工作区接口
def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generated_path(store: RunStore) -> Path:
    return store.dir / GENERATED_REL


def read_record(store: RunStore) -> dict[str, Any] | None:
    """读生成封面登记；不合格 → ValueError（看得见的错误，不静默重建）。"""
    path = store.dir / RECORD_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverError(f"{RECORD_FILE} 不可读：{exc}") from None
    if not isinstance(payload, dict):
        raise CoverError(f"{RECORD_FILE} 必须是 JSON 对象")
    return payload


def generate(
    store: RunStore,
    pub: Any,
    cfg: Any,
    *,
    out: str | Path | None = None,
    palette: str | None = None,
    imprint: str | None = None,
    size: str | None = None,
    dpi: int | None = None,
    pdf: bool = False,
    fonts: Fonts | None = None,
) -> dict[str, Any]:
    """生成封面并登记（CLI 入口）；返回含路径、尺寸、字体与降级信息的记录。"""
    spec = resolve_spec(
        pub,
        cfg,
        spec_file=read_spec_file(store),
        palette=palette,
        imprint=imprint,
        size=size,
    )
    fonts = fonts or find_fonts(
        cjk=cfg.cover.font_serif, latin=cfg.cover.font_latin, script=cfg.cover.imprint_font
    )
    dpi = int(dpi or cfg.cover.dpi)
    png = render_png(spec, fonts, dpi=dpi)

    target = generated_path(store)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    pdf_path = target.with_suffix(".pdf")
    pdf_bytes = render_pdf(spec, fonts) if pdf else None
    if pdf_bytes is not None:
        pdf_path.write_bytes(pdf_bytes)
    if out:
        # 额外导出（不改变登记位置）：--out 只是「顺手另存一份」
        exported = Path(out)
        exported.parent.mkdir(parents=True, exist_ok=True)
        exported.write_bytes(png)
        record_export = exported.as_posix()
        if pdf_bytes is not None:
            exported.with_suffix(".pdf").write_bytes(pdf_bytes)
    else:
        record_export = None

    # 源封面已确认时生成件不会被 build 使用：照做，但把「为什么看不到它」写进记录
    try:
        from .preprocess.cover import cover_status

        state = cover_status(store)
        source_cover = "confirmed" if state.get("confirmed") else None
    except ValueError:
        source_cover = None
    record = {
        "style": spec.style,
        "source_cover": source_cover,
        "palette": spec.palette,
        "size_mm": [round(spec.width * 25.4 / 72, 2), round(spec.height * 25.4 / 72, 2)],
        "dpi": dpi,
        "file": GENERATED_REL,
        "pdf": "structured/raw/media/cover-generated.pdf" if pdf_bytes else None,
        "export": record_export,
        "sha256": _digest(png),
        "design_digest": spec.digest(),
        "fonts": fonts.describe(),
        "text": {
            "title": spec.title,
            "subtitle": spec.subtitle,
            "original_title": spec.original_title,
            "original_subtitle": spec.original_subtitle,
            "credits": spec.credits,
            "lead": spec.lead,
            "series": spec.series,
            "imprint": spec.imprint,
        },
    }
    (store.dir / RECORD_FILE).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    store.log_event(
        "cover_generated",
        file=record["file"],
        palette=spec.palette,
        dpi=dpi,
        fonts=fonts.missing,
    )
    return record


def sync_for_build(store: RunStore, pub: Any, cfg: Any) -> dict[str, Any] | None:
    """构建期取用生成封面：登记存在且设计未变 → 复用；设计变了 → 重绘（不新建）。

    返回 ``{"epub_path": "media/cover-generated.png", "data": bytes}`` 或 None。
    没有登记就什么都不做——「没有源封面」不等于「必须造一个封面」。
    """
    record = read_record(store)
    if record is None:
        return None
    path = store.dir / str(record.get("file") or "")
    if not path.is_file():
        store.log_event("cover_generated_missing", file=str(record.get("file")))
        return None
    if str(record.get("file")) != GENERATED_REL:
        # 登记指向别处（agent 用 --out 导出到工作区外）：只认标准位置
        store.log_event("cover_generated_external", file=str(record.get("file")))
        return None
    data = path.read_bytes()
    spec = resolve_spec(pub, cfg, spec_file=read_spec_file(store))
    if record.get("design_digest") != spec.digest():
        if not cfg.cover.auto_sync:
            store.log_event("cover_generated_stale", file=GENERATED_REL)
            return None
        refreshed = generate(store, pub, cfg, dpi=cfg.cover.dpi)
        data = (store.dir / GENERATED_REL).read_bytes()
        store.log_event(
            "cover_regenerated", file=GENERATED_REL, design=refreshed["design_digest"][:12]
        )
    elif record.get("sha256") != _digest(data):
        store.log_event("cover_generated_tampered", file=GENERATED_REL)
    return {"epub_path": f"media/{Path(GENERATED_REL).name}", "data": data}
