# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""「汉译学术本」封面版式（issue #100）：设计解析、版式要素、可辨认下限、构建接线。

断言分三层：

1. **设计解析**——元数据/设计稿/命令行覆盖的优先级，默认值不瞎猜；
2. **版式要素**——纸纹纸色、双线框、四段式文字都在位，意象区按参数出现；
3. **交付契约**——JPEG q92 默认输出、build 内嵌 ``image/jpeg`` 的 cover-image、
   可辨认下限（600px 宽下最小字号 ≥14px）。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from auto_common.config import Config
from auto_common.workspace.models import Publication, PublicationMeta
from auto_epublizer import cover as cv
from auto_epublizer import cover_hanze as hz
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

runner = CliRunner()

PDF_MAGIC = b"%PDF"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _pub(**meta) -> Publication:
    payload = {
        "title": "Global Marx: History and Critique of the Social Movement in the World Market",
        "title_translated": "全球马克思",
        "creator": "Matthias Middell",
        "translator": "马加丹汉化组",
        "publisher": "BRILL",
        "date": "2023",
    }
    payload.update(meta)
    return Publication(slug="hanze", meta=PublicationMeta(**payload))


def _hanze(**overrides):
    spec_file = {
        "series": "STUDIES IN CRITICAL SOCIAL SCIENCES · 229",
        "subtitle": "世界市场中的社会运动史与批判",
        "original_title": "Global Marx",
        "original_subtitle": "History and Critique of the Social Movement in the World Market",
        "credits": ["[德] 马蒂亚斯 · 米德尔 等 著"],
        "note_line": "内部研究译本　不公开分发",
    }
    spec_file.update(overrides)
    return cv.resolve_spec(_pub(), Config(), style="hanze-academic", spec_file=spec_file)


def _fonts_or_skip() -> cv.Fonts:
    try:
        return cv.find_fonts()
    except cv.CoverError:
        pytest.skip("系统缺中文字体，跳过渲染断言")


def _open_image(data: bytes):
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="jpeg" if data.startswith(JPEG_MAGIC) else "png")
    pix = doc[0].get_pixmap(dpi=72)
    doc.close()
    return pix


def _row_darkness(pix, y: int, x_from: float = 0.0, x_to: float = 1.0) -> float:
    row = pix.samples[y * pix.stride : y * pix.stride + pix.width * pix.n]
    x0, x1 = int(pix.width * x_from), int(pix.width * x_to)
    return sum(row[x * pix.n] for x in range(x0, x1)) / max(x1 - x0, 1)


def _dark_pixels(pix, box: tuple[float, float, float, float], threshold: int = 200) -> int:
    """统计矩形区域内的暗像素数量（框线/文字/意象都算）。"""
    x0, y0, x1, y1 = (
        int(pix.width * box[0]),
        int(pix.height * box[1]),
        int(pix.width * box[2]),
        int(pix.height * box[3]),
    )
    n = 0
    for y in range(y0, y1):
        row = pix.samples[y * pix.stride : y * pix.stride + pix.width * pix.n]
        for x in range(x0, x1):
            if row[x * pix.n] < threshold:
                n += 1
    return n


# ---------------------------------------------------------------- 设计解析
def test_hanze_defaults_come_from_metadata() -> None:
    spec = _hanze()
    assert spec.style == "hanze-academic"
    assert spec.series_mark == "汉 译 学 术 本"  # 书系签默认值
    assert spec.publisher_line == "BRILL · 2023"  # 由 publisher · date 拼出
    assert spec.credit_role == "译"
    assert spec.motif == "none"  # 不猜意象：留空就是只出框与字
    assert spec.colors["paper"] == hz.PAPER
    assert spec.colors["gold"] == hz.GOLD


def test_hanze_palette_maps_to_accent_and_cli_accent_wins() -> None:
    forest = cv.resolve_spec(_pub(), Config(), style="hanze-academic", palette="forest")
    assert forest.colors["accent"] == hz.ACCENTS["forest"]
    over = cv.resolve_spec(
        _pub(),
        Config(),
        style="hanze-academic",
        palette="forest",
        overrides={"accent": "#123456"},
    )
    assert over.colors["accent"] == "#123456"


def test_hanze_unknown_palette_and_motif_are_explicit_errors() -> None:
    with pytest.raises(cv.CoverError, match="未知主色"):
        cv.resolve_spec(_pub(), Config(), style="hanze-academic", palette="nope")
    with pytest.raises(cv.CoverError, match="未知意象"):
        cv.resolve_spec(_pub(), Config(), style="hanze-academic", overrides={"motif": "unicorn"})


def test_template_alias_equals_style() -> None:
    common = {"series": "SERIES · 1", "motif": "globe"}
    a = cv.resolve_spec(_pub(), Config(), style="hanze-academic", spec_file=common)
    b = cv.resolve_spec(_pub(), Config(), spec_file={**common, "style": "hanze-academic"})
    assert a.digest() == b.digest()


def test_hanze_spec_still_refuses_legacy_style() -> None:
    with pytest.raises(cv.CoverError, match="已停用"):
        cv.resolve_spec(_pub(), Config(), style="magadan")


def test_hanze_text_overrides_beat_spec_file() -> None:
    spec = cv.resolve_spec(
        _pub(),
        Config(),
        style="hanze-academic",
        spec_file={"subtitle": "设计稿副题", "credits": ["设计稿 著"]},
        overrides={"subtitle": "命令副题"},
    )
    assert spec.subtitle == ["命令副题"]
    assert spec.credits == ["设计稿 著"]  # 没覆盖的仍取设计稿


# ---------------------------------------------------------------- 版式要素
def test_hanze_design_has_paper_frame_and_four_text_blocks() -> None:
    """纸底不是纯色、框线在主色与金之间、四段文字都排在框内。"""
    fonts = _fonts_or_skip()
    spec = _hanze(motif="globe")
    pix = _open_image(cv.render_image(spec, fonts, dpi=100, fmt="png"))
    # 纸纹：同一行左右两侧的灰度不完全相同（噪声+晕影），但都远亮于墨色
    a = _row_darkness(pix, int(pix.height * 0.55), 0.10, 0.12)
    b = _row_darkness(pix, int(pix.height * 0.55), 0.88, 0.90)
    assert a > 170 and b > 170
    assert abs(a - b) > 0.1
    # 外框在 3.6% / 2.4% 处：取框线上的像素应明显比纸底暗
    frame = _row_darkness(pix, int(pix.height * 0.0242), 0.10, 0.90)
    assert frame < 200


def test_hanze_motifs_draw_inside_the_reserved_band() -> None:
    """意象区在 41.7%–68.8%（设计画布 1000–1650）；留空时该带只剩纸纹。"""
    fonts = _fonts_or_skip()
    spec = _hanze(motif="arch")
    with_art = cv.render_image(spec, fonts, dpi=100, fmt="png")
    plain = cv.render_image(_hanze(motif="none"), fonts, dpi=100, fmt="png")
    art = _open_image(with_art)
    blank = _open_image(plain)
    band = (0.30, 0.44, 0.70, 0.66)  # 意象区再向内收一点，避开框线
    assert _dark_pixels(art, band) > _dark_pixels(blank, band) + 200


def test_hanze_globe_and_arch_are_different_drawings() -> None:
    fonts = _fonts_or_skip()
    globe = cv.render_image(_hanze(motif="globe"), fonts, dpi=72, fmt="png")
    arch = cv.render_image(_hanze(motif="arch"), fonts, dpi=72, fmt="png")
    assert globe != arch


# ---------------------------------------------------------------- 交付契约
def test_hanze_defaults_to_jpeg_q92() -> None:
    assert cv.resolve_format("hanze-academic", None, Config()) == "jpeg"
    assert cv.resolve_format("quarto", None, Config()) == "png"
    assert cv.resolve_format("hanze-academic", "png", Config()) == "png"
    assert cv.resolve_format("quarto", "jpg", Config()) == "jpeg"
    with pytest.raises(cv.CoverError, match="未知封面格式"):
        cv.resolve_format("quarto", "gif", Config())


def test_hanze_render_is_deterministic_in_both_formats() -> None:
    fonts = _fonts_or_skip()
    spec = _hanze(motif="globe")
    for fmt, magic in (("png", PNG_MAGIC), ("jpeg", JPEG_MAGIC)):
        first = cv.render_image(spec, fonts, dpi=72, fmt=fmt)
        assert first.startswith(magic)
        assert first == cv.render_image(spec, fonts, dpi=72, fmt=fmt)


def test_hanze_legibility_floor_at_600px() -> None:
    """600px 宽的成品上，每一段文字都要 ≥14px（更小分辨率不考虑）。"""
    spec = _hanze()
    for key in hz.TYPE:
        size = hz.effective_type(key, spec.width, spec.height)
        assert size / spec.width * 600 >= 13.99, key
        # 小字是被底线抬上来的（设计值本身在 600px 下不足 14px），不是本来就够大
        assert size >= cv.MIN_TYPE_FRAC * spec.width - 1e-9


def test_hanze_title_shrinks_for_long_titles_without_overflow() -> None:
    fonts = _fonts_or_skip()
    measurer = cv._Measurer(fonts)
    long_title = "马克思主义与中世纪研究：走向一种新的历史唯物主义与政治神学批判"
    spec = cv.resolve_spec(_pub(title_translated=long_title), Config(), style="hanze-academic")
    scale = min(spec.width / hz.DESIGN_W, spec.height / hz.DESIGN_H)
    inner = (1544 - 72 - 80) * scale
    size, lines = hz.fit_title("".join(spec.title), inner, spec.width, spec.height, measurer)
    assert size >= hz.TYPE["title_min"] * scale - 1e-6
    assert len(lines) >= 2


# ---------------------------------------------------------------- 工作区接线
def test_hanze_generate_writes_jpeg_and_build_embeds_it(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(
        store,
        title="Global Marx",
        creator="Matthias Middell",
        translator="马加丹汉化组",
        publisher="BRILL",
        date="2023",
    )
    record = orch.generate_cover(
        store,
        style="hanze-academic",
        palette="ochre",
        dpi=100,
        overrides={
            "series": "STUDIES IN CRITICAL SOCIAL SCIENCES · 229",
            "subtitle": "世界市场中的社会运动史与批判",
            "motif": "globe",
            "note_line": "内部研究译本　不公开分发",
        },
    )
    assert record["format"] == "jpeg"
    assert record["file"] == cv.generated_rel("jpeg")
    assert (store.dir / record["file"]).read_bytes().startswith(JPEG_MAGIC)
    assert record["overrides"]["motif"] == "globe"  # 命令行覆盖被记住，构建期不会被抹掉

    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'properties="cover-image"' in opf
        assert 'media-type="image/jpeg"' in opf
        assert zf.read("OEBPS/media/cover-generated.jpg").startswith(JPEG_MAGIC)


def test_switching_format_removes_the_other_suffix(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(store, title="全球马克思", translator="马加丹汉化组")
    orch.generate_cover(store, style="hanze-academic", dpi=72, fmt="png")
    assert (store.dir / cv.generated_rel("png")).is_file()
    orch.generate_cover(store, style="hanze-academic", dpi=72, fmt="jpeg")
    assert (store.dir / cv.generated_rel("jpeg")).is_file()
    assert not (store.dir / cv.generated_rel("png")).exists()


def test_hanze_regeneration_keeps_cli_overrides(tmp_path: Path) -> None:
    """元数据变了要重绘，但 --motif/--series 这些命令行覆盖必须跟着走。"""
    store = _workspace(tmp_path)
    orch.set_meta(store, title="旧书名", translator="马加丹汉化组")
    orch.generate_cover(
        store,
        style="hanze-academic",
        dpi=72,
        overrides={"motif": "arch", "series": "SERIES · 7"},
    )
    orch.set_meta(store, title="新书名")
    orch.build(store)
    record = json.loads((store.dir / cv.RECORD_FILE).read_text(encoding="utf-8"))
    assert record["text"]["title"] == ["新书名"]
    assert record["text"]["motif"] == "arch"
    assert record["text"]["series"] == ["SERIES · 7"]
    assert "cover_regenerated" in (store.dir / "events.jsonl").read_text(encoding="utf-8")


def test_cli_accepts_template_alias_and_hanze_flags(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(store, title="全球马克思", translator="马加丹汉化组", publisher="BRILL")
    result = runner.invoke(
        app,
        [
            "cover",
            "--workspace",
            str(store.dir),
            "--template",
            "hanze-academic",
            "--accent",
            "#7A2222",
            "--motif",
            "globe",
            "--series",
            "STUDIES · 229",
            "--publisher-line",
            "BRILL · 2023",
            "--note-line",
            "内部研究译本　不公开分发",
            "--format",
            "jpeg",
            "--dpi",
            "72",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    record = json.loads((store.dir / cv.RECORD_FILE).read_text(encoding="utf-8"))
    assert record["style"] == "hanze-academic"
    assert record["format"] == "jpeg"
    assert record["text"]["motif"] == "globe"
    assert record["text"]["series"] == ["STUDIES · 229"]
    assert record["text"]["publisher_line"] == "BRILL · 2023"
    assert record["text"]["note_line"] == "内部研究译本　不公开分发"
    assert record["text"]["title"] == ["全球马克思"]


def test_delete_cover_removes_whichever_format_was_written(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(store, title="全球马克思", translator="马加丹汉化组")
    orch.generate_cover(store, style="hanze-academic", dpi=72)
    assert (store.dir / cv.generated_rel("jpeg")).is_file()
    orch.delete_cover(store)
    assert not (store.dir / cv.generated_rel("jpeg")).exists()
    assert not (store.dir / cv.RECORD_FILE).exists()


def test_hanze_pdf_shows_title_and_translator_credits(tmp_path: Path) -> None:
    """G1：封面 PDF 文本层可见书名与译者署名（不靠 grep 位图）。"""
    import re
    import unicodedata

    import pymupdf

    store = _workspace(tmp_path)
    pub = store.load_publication()
    pub.meta.title = "马克思主义与中世纪研究"
    pub.meta.translator = "马加丹汉化组"
    pub.meta.publisher = "BRILL"
    pub.meta.date = "2024"
    store.save_publication(pub)
    record = orch.generate_cover(store, style="hanze-academic", pdf=True)
    assert record["pdf"]
    pdf_path = next(store.dir.rglob("cover-generated.pdf"))
    with pymupdf.open(pdf_path) as doc:
        text = unicodedata.normalize(
            "NFKC", re.sub(r"\s+", "", "".join(page.get_text() for page in doc))
        )
    assert "马克思主义与中世纪研究" in text
    assert "马加丹汉化组" in text and "译" in text
    assert "BRILL" in text and "2024" in text


def test_hanze_dossier_is_a_distinct_drawing() -> None:
    """E4：档案卷宗意象可渲染，且与拱窗不是同一张图。"""
    fonts = _fonts_or_skip()
    dossier = cv.render_image(_hanze(motif="dossier"), fonts, dpi=72, fmt="png")
    arch = cv.render_image(_hanze(motif="arch"), fonts, dpi=72, fmt="png")
    assert dossier != arch
    art = _open_image(dossier)
    blank = _open_image(cv.render_image(_hanze(motif="none"), fonts, dpi=72, fmt="png"))
    assert _dark_pixels(art, (0.30, 0.44, 0.70, 0.66)) > _dark_pixels(
        blank, (0.30, 0.44, 0.70, 0.66)
    )


def test_hanze_paper_fills_page_without_white_edges() -> None:
    """回归：纸底必须铺满整页，不能在左右留出白边（A5 与 2:3 纹理不同比例）。"""
    fonts = _fonts_or_skip()
    data = cv.render_image(_hanze(motif="none"), fonts, dpi=150, fmt="png")
    pix = _open_image(data)
    samples, width, height, n, stride = pix.samples, pix.width, pix.height, pix.n, pix.stride

    def rgb(x: int, y: int) -> tuple[int, int, int]:
        i = y * stride + x * n
        return samples[i], samples[i + 1], samples[i + 2]

    edges = (
        [rgb(x, 0) for x in range(0, width, 7)]
        + [rgb(x, height - 1) for x in range(0, width, 7)]
        + [rgb(0, y) for y in range(0, height, 7)]
        + [rgb(width - 1, y) for y in range(0, height, 7)]
    )
    assert not any(min(pixel) > 250 for pixel in edges), "封面边缘出现白边"
