# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""生成式书封（quarto「界栏」版式）：metadata + 设计稿 → 确定性 PNG/PDF。

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

版式（``quarto``，中文名「界栏」）：整幅深色底面 + 反白左对齐大字号书名 +
左侧双线界栏 + 标题下短横 + 斜体原文名 + 左下责任者 + 右下署名。整本书靠色板
（底面/文字/强调三色）分家，同一批书既统一又互不雷同。

**可辨认底线**：成品最窄按 600px 宽看（更小的分辨率不考虑）。中文衬线字身低于
约 14px 就糊成一团，所以本模块所有字号都必须 ≥ ``MIN_TYPE_FRAC``（= 14/600 ≈
2.34% 页宽 = A5 上 9.8pt）。改版式比例可以，别把字号压到这条线以下——
``tests/test_cover_render.py`` 会拦。

比例见 ``QUARTO_GEOM``/``QUARTO_TYPE``；改这些常数等于改版式，改动后请重跑
``tests/test_cover_render.py`` 的对版与可辨认断言。

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
GENERATED_STEM = "structured/raw/media/cover-generated"
#: 输出格式：PNG（版式色块锐利）或 JPEG（纸纹照片感、体积小；hanze-academic 默认）。
FORMATS: tuple[str, ...] = ("png", "jpeg")
JPEG_QUALITY = 92


def generated_rel(fmt: str = "png") -> str:
    """生成封面在工作区内的相对路径（按格式换后缀）。"""
    return f"{GENERATED_STEM}.jpg" if fmt == "jpeg" else f"{GENERATED_STEM}.png"


GENERATED_REL = generated_rel("png")

#: 版式名：quarto（界栏，默认）与 hanze-academic（汉译学术本，issue #100）。
#: 旧的 magadan 版式已停用；记录与摘要里仍保留 style 字段以便追溯。
STYLE = "quarto"
DEFAULT_STYLE = "quarto"
STYLES: tuple[str, ...] = ("quarto", "hanze-academic")

#: 可辨认底线：600px 宽的成品上，最小字号的字身不得低于 14px（CJK 衬线）。
LEGIBILITY_EM_PX = 14.0
LEGIBILITY_REF_WIDTH_PX = 600.0
MIN_TYPE_FRAC = LEGIBILITY_EM_PX / LEGIBILITY_REF_WIDTH_PX  # ≈ 0.02333（页宽比例）

#: 色板：quarto 用「底面 / 文字 / 强调」三色。整本书靠色板区分，版式保持一致。
PALETTES: dict[str, dict[str, str]] = {
    "ink": {"field": "#171A20", "type": "#F5F0E6", "accent": "#C9A227"},
    "oxblood": {"field": "#5B1B22", "type": "#F2EADD", "accent": "#D8B26E"},
    "forest": {"field": "#1D3A2F", "type": "#F1EDDF", "accent": "#CBB27A"},
    "indigo": {"field": "#1B2A55", "type": "#F3EFE4", "accent": "#C9B37E"},
    "aubergine": {"field": "#3A2340", "type": "#F3ECEE", "accent": "#D9A7A0"},
    "slate": {"field": "#22333B", "type": "#F0EEE7", "accent": "#A8C3B5"},
    "rust": {"field": "#6B2E17", "type": "#F5EDDF", "accent": "#E3C08A"},
    # 浅色版：纸底墨字，印得省、看着轻，适合同一批里的「轻」书
    "paper": {"field": "#F4EFE3", "type": "#1A1A1A", "accent": "#8A2B2B"},
}

#: quarto 版式比例（页宽 W / 页高 H）：整幅底面、左界栏、左对齐书名群。
QUARTO_GEOM = {
    "margin": 0.090,  # 左右版心边距
    "spine_x": 0.062,  # 左侧界栏主线位置
    "spine_top": 0.055,
    "spine_bottom": 0.945,
    "series_top": 0.085,  # 丛书名基线
    "title_top": 0.255,  # 书名墨迹顶
    "title_min": 0.048,  # 书名自动缩排下限（/ 页宽）
    "lead_gap": 0.028,  # 书名上方小字与书名
    "rule_gap": 0.030,  # 书名下短横
    "rule_w": 0.30,  # 短横长度（/ 页宽）
    "sub_gap": 0.030,  # 短横与副书名
    "orig_gap": 0.050,  # 副书名与原文名
    "origsub_gap": 0.014,  # 原文名与原文副名
    "credits_bottom": 0.878,  # 责任者行末行墨迹底
    "credits_leading": 1.55,
    "foot_rule": 0.906,
    "imprint_baseline": 0.940,
    "title_leading": 1.06,
}

#: quarto 版式字号（/ 页宽）。**每一项都必须 ≥ MIN_TYPE_FRAC**（600px 宽下 ≥14px）。
QUARTO_TYPE = {
    "series": 0.0245,  # 600px 下 ≈ 14.7px
    "lead": 0.0260,  # ≈ 15.6px
    "title": 0.0960,  # 基准 57.6px；短书名可放到 1.45×，长书名收到 0.75×
    "subtitle": 0.0305,  # ≈ 18.3px
    "original_title": 0.0275,  # ≈ 16.5px
    "original_subtitle": 0.0250,  # ≈ 15.0px
    "credits": 0.0240,  # ≈ 14.4px（全篇最小）
    "imprint": 0.0260,  # ≈ 15.6px
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
    latin_italic: Path | None = None
    missing: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        return {
            "cjk": self.cjk.name,
            "latin": self.latin.name if self.latin else None,
            "italic": self.latin_italic.name if self.latin_italic else None,
            "script": self.script.name if self.script else None,
            "missing": list(self.missing),
        }


def _italic_sibling(path: Path | None) -> Path | None:
    """同一家族的斜体文件（拉丁衬线的斜体常与常规同目录同前缀）。"""
    if path is None:
        return None
    stem = path.stem
    for marker in ("-Regular", "Regular", "-Book", "-Roman"):
        if not stem.endswith(marker):
            continue
        base = stem[: -len(marker)]
        for suffix in ("-Italic", "-Oblique", "Italic", " Italic", "-ItalicMT"):
            for ext in (path.suffix, ".otf", ".ttf"):
                candidate = path.with_name(f"{base}{suffix}{ext}")
                if candidate.is_file():
                    return candidate
    return None


@dataclass(frozen=True)
class CoverSpec:
    """一份可渲染的封面设计（已解析、已换行切分、已算好字号）。"""

    width: float
    height: float
    #: 颜色角色：field（底面）/ type（文字）/ accent（强调）
    colors: dict[str, str]
    title: list[str]
    subtitle: list[str] = field(default_factory=list)
    original_title: list[str] = field(default_factory=list)
    original_subtitle: list[str] = field(default_factory=list)
    credits: list[str] = field(default_factory=list)
    lead: list[str] = field(default_factory=list)
    series: list[str] = field(default_factory=list)
    imprint: str = ""
    #: 署名后缀（「马加丹汉化组　译」里的「译」）；空串=只写署名
    credit_role: str = "译"
    #: 仅 hanze-academic：意象种类（none / globe / arch）
    motif: str = "none"
    #: 仅 hanze-academic：书系签（默认「汉 译 学 术 本」）
    series_mark: str = ""
    #: 仅 hanze-academic：出版行（如「BRILL · 2023」）
    publisher_line: str = ""
    #: 仅 hanze-academic：免责行（如「内部研究译本　不公开分发」）
    note_line: str = ""
    style: str = STYLE
    palette: str = "ink"

    def digest(self) -> str:
        """设计摘要：内容一变，构建期就能发现封面过期。"""
        payload = {
            "style": self.style,
            "palette": self.palette,
            "size": [round(self.width, 3), round(self.height, 3)],
            "colors": sorted(self.colors.items()),
            "texts": [
                self.title,
                self.subtitle,
                self.original_title,
                self.original_subtitle,
                self.credits,
                self.lead,
                self.series,
                self.imprint,
                self.credit_role,
                self.motif,
                self.series_mark,
                self.publisher_line,
                self.note_line,
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
    return Fonts(
        cjk=cjk_path,
        latin=latin_path,
        script=script_path,
        latin_italic=_italic_sibling(latin_path),
        missing=tuple(missing),
    )


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


def resolve_format(style_name: str, fmt: str | None = None, cfg: Any = None) -> str:
    """决定输出格式：显式 > 配置 > 版式默认（hanze 用 JPEG，其余 PNG）。"""
    name = str(fmt or getattr(getattr(cfg, "cover", None), "format", "") or "").strip().lower()
    if not name:
        name = "jpeg" if style_name == "hanze-academic" else "png"
    if name in ("jpg", "jpeg"):
        return "jpeg"
    if name == "png":
        return "png"
    raise CoverError(f"未知封面格式：{name}（可选 {', '.join(FORMATS)}）")


def resolve_spec(
    pub: Any,
    cfg: Any,
    *,
    spec_file: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
    palette: str | None = None,
    imprint: str | None = None,
    size: str | None = None,
    style: str | None = None,
) -> CoverSpec:
    """元数据 + 设计稿 + 命令行覆盖 → CoverSpec（不渲染、不落盘）。

    ``spec_file`` 是 agent 手写的设计稿；``overrides`` 是命令行一次性覆盖
    （``--accent``/``--motif``/``--series`` 等），后者优先。
    """
    from auto_epublizer.pdfexport import SIZES

    overrides = {**(spec_file or {}), **(overrides or {})}
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

    style_name = str(style or overrides.get("style") or cfg.cover.style or DEFAULT_STYLE)
    if style_name == "magadan":
        raise CoverError("旧版式 magadan 已停用，统一用 quarto/界栏 或 hanze-academic/汉译学术本")
    if style_name not in STYLES:
        raise CoverError(f"未知版式：{style_name}（可选 {', '.join(STYLES)}）")

    palette_name = str(
        palette
        or overrides.get("palette")
        or cfg.cover.palette
        or ("ink" if style_name == "quarto" else "ochre")
    )
    if style_name == "quarto":
        if palette_name not in PALETTES:
            raise CoverError(f"未知色板：{palette_name}（可选 {', '.join(PALETTES)}）")
        colors = dict(PALETTES[palette_name])
    else:
        from . import cover_hanze as hz

        accent = str(overrides.get("accent") or "").strip()
        if not accent and palette_name in hz.ACCENTS:
            accent = hz.ACCENTS[palette_name]
        if not accent:
            raise CoverError(
                f"未知主色：{palette_name}（可选 {', '.join(hz.ACCENTS)}，或直接用 --accent #RRGGBB）"
            )
        colors = {
            "paper": hz.PAPER,
            "gold": hz.GOLD,
            "ink": hz.INK_C,
            "muted": hz.MUTED,
            "faint": hz.FAINT,
            "orig": hz.ORIG,
            "orig_sub": hz.ORIG_SUB,
            "accent": accent,
        }

    size_name = str(size or overrides.get("size") or cfg.cover.size or "a5").lower()
    if size_name not in SIZES:
        raise CoverError(f"未知开本：{size_name}（可选 {', '.join(SIZES)}）")
    mm_w, mm_h = SIZES[size_name]
    width = mm_w * 72 / 25.4
    height = mm_h * 72 / 25.4

    if imprint is not None:
        imprint_text = imprint
    elif "imprint" in overrides:
        imprint_text = str(overrides["imprint"])
    else:
        imprint_text = cfg.cover.imprint or ""

    from . import cover_hanze as _hz

    motif = str(overrides.get("motif") or "none").lower()
    if motif in ("", "off", "none"):
        motif = "none"
    elif motif not in _hz.MOTIFS:
        raise CoverError(f"未知意象：{motif}（可选 {', '.join(_hz.MOTIFS)}）")
    series_mark = str(overrides.get("series_mark") or "")
    publisher_line = str(overrides.get("publisher_line") or "").strip()
    if not publisher_line and style_name == "hanze-academic":
        bits = [str(meta.publisher or "").strip(), str(meta.date or "").strip()]
        publisher_line = " · ".join(b for b in bits if b)
    if style_name == "hanze-academic" and not series_mark:
        series_mark = "汉 译 学 术 本"

    return CoverSpec(
        width=width,
        height=height,
        colors=colors,
        title=_lines(title_text),
        subtitle=_lines(overrides.get("subtitle") or ""),
        original_title=_lines(original or ""),
        original_subtitle=_lines(overrides.get("original_subtitle") or ""),
        credits=_flatten(overrides.get("credits") or _default_credits(meta)),
        lead=_lines(overrides.get("lead") or ""),
        series=_lines(overrides.get("series") or ""),
        imprint=str(imprint_text).strip(),
        credit_role=str(overrides.get("credit_role") or "译"),
        motif=motif,
        series_mark=series_mark,
        publisher_line=publisher_line,
        note_line=str(overrides.get("note_line") or ""),
        style=style_name,
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
        self._italic = (
            pymupdf.Font(fontfile=str(fonts.latin_italic)) if fonts.latin_italic else self._latin
        )
        self._script = pymupdf.Font(fontfile=str(fonts.script)) if fonts.script else self._cjk

    @property
    def cjk(self) -> pymupdf.Font:
        return self._cjk

    @property
    def latin(self) -> pymupdf.Font:
        return self._latin

    @property
    def italic(self) -> pymupdf.Font:
        return self._italic

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


def _mix(color: str, base: str, alpha: float) -> tuple[float, float, float]:
    """把 ``color`` 按 ``alpha`` 混到 ``base`` 上（等价于低不透明度，但直接给 RGB）。

    MuPDF 的填充色只认 RGB 三元组（四元组会被当成 CMYK，白会变黑），因此这里预先
    混色，而不是靠 opacity。
    """
    top = _hex(color)
    bottom = _hex(base)
    return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3))  # type: ignore[return-value]


def _quarto_layout(
    spec: CoverSpec, measurer: _Measurer, fonts: Fonts, scale: float
) -> tuple[list[tuple], list[tuple], bool]:
    """算 quarto 版式的绘制指令；返回 (文字指令, 线条指令, 是否放得下)。

    文字指令：``(text, size, x, baseline, color_rgb, kind, tracking)``，
    ``kind`` 取 ``auto``（按字符自动选中文/拉丁）、``italic``、``script``。
    线条指令：``(x0, y0, x1, y1, color_rgb, width)``
    先算再画，才能在「书名群过长会顶到责任者」时整体缩一档重排（见 ``_draw_quarto``）。
    """
    W, H = spec.width, spec.height
    colors = spec.colors
    field, type_c, accent = colors["field"], colors["type"], colors["accent"]
    left = QUARTO_GEOM["margin"] * W
    right = W - left
    measure = right - left
    ink = _hex(type_c)

    texts: list[tuple] = []
    rules: list[tuple] = []

    def text(line, size, x, baseline, color, kind="auto", tracking=0.0):
        # 可辨认下限是硬约束：任何元素都不许被缩到 600px 宽下糊掉
        texts.append((line, max(size, MIN_TYPE_FRAC * W), x, baseline, color, kind, tracking))

    if spec.series:
        size = QUARTO_TYPE["series"] * W
        baseline = QUARTO_GEOM["series_top"] * H
        chip = size * 0.60
        rules.append(
            (
                left,
                baseline - chip * 0.72,
                left + chip,
                baseline - chip * 0.72 + chip,
                _hex(accent),
                0.0,
            )
        )
        text(" ".join(spec.series), size, left + size * 1.9, baseline, _hex(accent), tracking=0.16)

    y = QUARTO_GEOM["title_top"] * H
    if spec.lead:
        size = QUARTO_TYPE["lead"] * W * scale
        text(
            " ".join(spec.lead),
            size,
            left,
            y + INK["cjk"][0] * size,
            _mix(type_c, field, 0.92),
            tracking=0.05,
        )
        y += (INK["cjk"][0] + INK["cjk"][1]) * size + QUARTO_GEOM["lead_gap"] * H

    # 书名自适应：短书名涨到版心的 88%（最多 1.45 倍），长书名收到 0.75 倍后折行——
    # 「字少就大、字多就稳」，同批书摆一起不会有的满版有的缩成小字。
    base_title = QUARTO_TYPE["title"] * W * scale
    unit_w = max(measurer.width(line, 100.0) for line in spec.title) / 100.0
    fill_size = measure * 0.88 / max(unit_w, 1e-6)
    title_size = min(max(fill_size, base_title * 0.75), base_title * 1.45)
    title_size = max(title_size, QUARTO_GEOM["title_min"] * W)
    title_lines: list[str] = []
    for line in spec.title:
        title_lines.extend(wrap(line, measure, title_size, measurer) or [line])
    baseline = y + INK["cjk"][0] * title_size
    for index, line in enumerate(title_lines):
        if index:
            baseline += QUARTO_GEOM["title_leading"] * title_size
        text(line, title_size, left, baseline, ink)
    y = baseline + INK["cjk"][1] * title_size

    y += QUARTO_GEOM["rule_gap"] * H
    rules.append((left, y, left + QUARTO_GEOM["rule_w"] * W, y, _hex(accent), 1.2))
    y += QUARTO_GEOM["sub_gap"] * H

    def block(lines: list[str], key: str, alpha: float, leading: float, italic: bool = False):
        nonlocal y
        size = QUARTO_TYPE[key] * W * scale
        for line in lines:
            for piece in wrap(line, measure, size, measurer) or [line]:
                cjk = any(_is_cjk(ch) for ch in piece)
                top, bottom = INK["cjk"] if cjk else INK["latin"]
                base = y + top * size
                text(
                    piece,
                    size,
                    left,
                    base,
                    _mix(type_c, field, alpha),
                    kind="italic" if italic else "auto",
                )
                y = base + bottom * size
                y += (leading - 1) * size

    if spec.subtitle:
        block(spec.subtitle, "subtitle", 0.88, 1.32)
        y += QUARTO_GEOM["orig_gap"] * H
    if spec.original_title:
        block(spec.original_title, "original_title", 0.60, 1.25, italic=True)
        y += QUARTO_GEOM["origsub_gap"] * H
    if spec.original_subtitle:
        block(spec.original_subtitle, "original_subtitle", 0.46, 1.30)

    # 责任者：从下往上排，最后一行贴住 credits_bottom
    credits_lines: list[str] = []
    if spec.credits:
        size = QUARTO_TYPE["credits"] * W
        for line in spec.credits:
            credits_lines.extend(wrap(line, measure, size, measurer) or [line])
        leading = QUARTO_GEOM["credits_leading"] * size
        base = QUARTO_GEOM["credits_bottom"] * H
        for line in reversed(credits_lines):
            text(line, size, left, base, _mix(type_c, field, 0.70))
            base -= leading
        credits_top = base + leading
    else:
        credits_top = QUARTO_GEOM["credits_bottom"] * H

    rules.append(
        (
            left,
            QUARTO_GEOM["foot_rule"] * H,
            right,
            QUARTO_GEOM["foot_rule"] * H,
            _mix(type_c, field, 0.16),
            0.4,
        )
    )

    if spec.imprint:
        size = QUARTO_TYPE["imprint"] * W
        has_script = fonts.script is not None
        tracking = 0.0 if has_script else 0.10
        width = measurer.width(spec.imprint, size, script=has_script) + (
            tracking * size * len(spec.imprint)
        )
        text(
            spec.imprint,
            size,
            right - width,
            QUARTO_GEOM["imprint_baseline"] * H,
            _hex(accent),
            kind="script" if has_script else "auto",
            tracking=tracking,
        )

    fits = y <= credits_top - 0.03 * H
    return texts, rules, fits


def _draw(spec: CoverSpec, fonts: Fonts) -> pymupdf.Document:
    """按 ``spec.style`` 分派到具体版式。"""
    if spec.style == "hanze-academic":
        from . import cover_hanze

        return cover_hanze.draw(spec, fonts)
    return _draw_quarto(spec, fonts)


def _draw_quarto(spec: CoverSpec, fonts: Fonts) -> pymupdf.Document:
    """quarto（界栏）：整幅底面 + 反白书名 + 双线界栏 + 短横 + 斜体原文名。"""
    measurer = _Measurer(fonts)
    W, H = spec.width, spec.height
    scale = 1.0
    texts: list[tuple] = []
    rules: list[tuple] = []
    for _attempt in range(3):
        texts, rules, fits = _quarto_layout(spec, measurer, fonts, scale)
        if fits:
            break
        scale *= 0.90  # 书名群顶到责任者时整体缩一档，绝不叠字

    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    # 背景略超出页面 1pt：避免栅格化时最外一列抗锯齿留白（白边）。
    page.draw_rect(
        pymupdf.Rect(-1, -1, W + 1, H + 1), color=None, fill=_hex(spec.colors["field"]), width=0
    )

    # 左侧界栏：一粗一细两条竖线（书口/版框的意思）
    spine_x = QUARTO_GEOM["spine_x"] * W
    page.draw_line(
        pymupdf.Point(spine_x, QUARTO_GEOM["spine_top"] * H),
        pymupdf.Point(spine_x, QUARTO_GEOM["spine_bottom"] * H),
        color=_mix(spec.colors["accent"], spec.colors["field"], 0.55),
        width=0.7,
    )
    page.draw_line(
        pymupdf.Point(spine_x - 3.4, QUARTO_GEOM["spine_top"] * H),
        pymupdf.Point(spine_x - 3.4, QUARTO_GEOM["spine_bottom"] * H),
        color=_mix(spec.colors["type"], spec.colors["field"], 0.22),
        width=0.4,
    )

    for x0, y0, x1, y1, color, width in rules:
        if width <= 0:  # 色块（丛书名前的小方点）
            page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=None, fill=color, width=0)
        else:
            page.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1), color=color, width=width)

    # 同一颜色的文字合到一个 TextWriter 里（TextWriter 每次 write 只认一种颜色）
    writers: dict[tuple, pymupdf.TextWriter] = {}
    for line, size, x, baseline, color, kind, tracking in texts:
        key = tuple(round(c, 6) for c in color)
        tw = writers.get(key)
        if tw is None:
            tw = writers[key] = pymupdf.TextWriter(page.rect)
        if kind == "script":
            font = measurer.script
        elif kind == "italic":
            font = measurer.italic or measurer.latin
        else:
            font = measurer.cjk if any(_is_cjk(ch) for ch in line) else measurer.latin
        cursor = x
        for ch in line:
            tw.append((cursor, baseline), ch, font=font, fontsize=size)
            cursor += font.text_length(ch, fontsize=size) + tracking * size
    for color, tw in writers.items():
        tw.write_text(page, color=color)
    return doc


def render_image(spec: CoverSpec, fonts: Fonts, *, dpi: int = 300, fmt: str = "png") -> bytes:
    """渲染为位图字节（确定性：同输入同输出）；``fmt`` 取 png / jpeg。"""
    if dpi < 72 or dpi > 1200:
        raise CoverError(f"dpi 超出范围（72–1200）：{dpi}")
    fmt = resolve_format(spec.style, fmt)
    doc = _draw(spec, fonts)
    try:
        pixmap = doc[0].get_pixmap(dpi=dpi)
        if fmt == "jpeg":
            return pixmap.tobytes("jpg", jpg_quality=JPEG_QUALITY)
        return pixmap.tobytes("png")
    finally:
        doc.close()


def render_png(spec: CoverSpec, fonts: Fonts, *, dpi: int = 300) -> bytes:
    """渲染为 PNG 字节（``render_image`` 的薄包装，保留旧名字）。"""
    return render_image(spec, fonts, dpi=dpi, fmt="png")


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
    style: str | None = None,
    palette: str | None = None,
    imprint: str | None = None,
    size: str | None = None,
    dpi: int | None = None,
    pdf: bool = False,
    fonts: Fonts | None = None,
    overrides: dict[str, Any] | None = None,
    fmt: str | None = None,
) -> dict[str, Any]:
    """生成封面并登记（CLI 入口）；返回含路径、尺寸、字体与降级信息的记录。

    ``overrides`` 是一次性设计覆盖（``--accent``/``--motif``/``--series`` 等），
    会原样存进登记，构建期重绘时照用，避免「命令行调过的版式被 auto_sync 抹掉」。
    """
    one_shot = {
        k: v
        for k, v in {
            "style": style,
            "palette": palette,
            "size": size,
            **(overrides or {}),
        }.items()
        if v not in (None, "")
    }
    if imprint is not None and str(imprint).strip():
        one_shot["imprint"] = imprint
    spec = resolve_spec(pub, cfg, spec_file=read_spec_file(store), overrides=one_shot)
    fonts = fonts or find_fonts(
        cjk=cfg.cover.font_serif, latin=cfg.cover.font_latin, script=cfg.cover.imprint_font
    )
    dpi = int(dpi or cfg.cover.dpi)
    fmt = resolve_format(spec.style, fmt, cfg)
    data = render_image(spec, fonts, dpi=dpi, fmt=fmt)

    rel = generated_rel(fmt)
    target = store.dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    # 换过格式就把另一种后缀的旧件清掉，免得 build 看到两版封面
    for other in FORMATS:
        stale = store.dir / generated_rel(other)
        if stale != target and stale.is_file():
            stale.unlink()
    pdf_path = target.with_suffix(".pdf")
    pdf_bytes = render_pdf(spec, fonts) if pdf else None
    if pdf_bytes is not None:
        pdf_path.write_bytes(pdf_bytes)
    if out:
        # 额外导出（不改变登记位置）：--out 只是「顺手另存一份」
        exported = Path(out)
        exported.parent.mkdir(parents=True, exist_ok=True)
        exported.write_bytes(data)
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
        "format": fmt,
        "file": rel,
        "pdf": f"{GENERATED_STEM}.pdf" if pdf_bytes else None,
        "export": record_export,
        "sha256": _digest(data),
        "design_digest": spec.digest(),
        "overrides": one_shot,
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
            "motif": spec.motif,
            "series_mark": spec.series_mark,
            "publisher_line": spec.publisher_line,
            "note_line": spec.note_line,
            "credit_role": spec.credit_role,
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
    rel = str(record.get("file") or "")
    path = store.dir / rel
    if not path.is_file():
        store.log_event("cover_generated_missing", file=rel)
        return None
    if rel not in (generated_rel("png"), generated_rel("jpeg")):
        # 登记指向别处（agent 用 --out 导出到工作区外）：只认标准位置
        store.log_event("cover_generated_external", file=rel)
        return None
    data = path.read_bytes()
    stored = record.get("overrides")
    spec = resolve_spec(
        pub,
        cfg,
        spec_file=read_spec_file(store),
        overrides=stored if isinstance(stored, dict) else {},
    )
    if record.get("design_digest") != spec.digest():
        if not cfg.cover.auto_sync:
            store.log_event("cover_generated_stale", file=rel)
            return None
        refreshed = generate(
            store,
            pub,
            cfg,
            dpi=cfg.cover.dpi,
            fmt=record.get("format"),
            overrides=stored if isinstance(stored, dict) else None,
        )
        rel = refreshed["file"]
        data = (store.dir / rel).read_bytes()
        store.log_event("cover_regenerated", file=rel, design=refreshed["design_digest"][:12])
    elif record.get("sha256") != _digest(data):
        store.log_event("cover_generated_tampered", file=rel)
    return {"epub_path": f"media/{Path(rel).name}", "data": data}
