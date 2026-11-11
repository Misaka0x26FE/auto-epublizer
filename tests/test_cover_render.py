# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""生成式书封（quarto/界栏版式）：设计解析、排版对版、可辨认下限、构建接线。

对版断言用「墨迹位置」而不是像素比对：版式比例的权威来源是参考样张的实测，
这里守住的就是那几组比例（色带、书名群起点、右边界、署名）不被无意改掉。
渲染依赖系统 CJK 字体（CI 装 fonts-noto-cjk）；无字体环境跳过渲染类断言，
但仍验证纯逻辑（设计解析/校验/登记/撤销）。
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
from auto_epublizer import orchestrator as orch
from auto_epublizer.cli import app

runner = CliRunner()


# ---------------------------------------------------------------- 工具
def _workspace(tmp_path: Path):
    src = tmp_path / "book.md"
    src.write_text("# 第一章\n\n正文。\n", encoding="utf-8")
    return orch.init(str(src), workspace_dir=str(tmp_path / "ws"))


def _pub(**meta) -> Publication:
    payload = {"title": "Reordering of Meaningful Worlds", "title_translated": "重构意义世界"}
    payload.update(meta)
    return Publication(slug="demo", meta=PublicationMeta(**payload))


def _pixels(png: bytes, dpi: int = 72):
    import pymupdf

    doc = pymupdf.open(stream=png, filetype="png")
    pix = doc[0].get_pixmap(dpi=dpi)
    return pix.samples, pix.width, pix.height, pix.n, pix.stride


def _ink_rows(
    png: bytes,
    *,
    x_from: float = 0.03,
    x_to: float = 0.885,
    light: bool = False,
    dpi: int = 72,
    threshold: int = 128,
    y_to: float = 0.995,
) -> tuple[list, int, int]:
    """按行统计「有字」的像素（默认深字浅底；``light=True`` 用于浅字深底）。

    返回 (行区间列表, 宽, 高)；纯 pymupdf 读图，无额外依赖。
    """
    samples, width, height, n, stride = _pixels(png, dpi)
    x0, x1 = int(width * x_from), int(width * x_to)
    runs: list[tuple[int, int]] = []
    current: list[int] | None = None
    for y in range(min(height, int(height * y_to))):
        row = samples[y * stride : y * stride + width * n]
        dark = any(
            (row[x * n] > threshold) if light else (row[x * n] < threshold) for x in range(x0, x1)
        )
        if dark:
            current = [y, y] if current is None else [current[0], y]
        elif current is not None:
            if current[1] - current[0] >= 4:
                runs.append((current[0], current[1]))
            current = None
    if current is not None:
        runs.append((current[0], current[1]))
    return runs, width, height


def _fonts_or_skip() -> cv.Fonts:
    try:
        return cv.find_fonts()
    except cv.CoverError:  # 无 CJK 字体的环境：渲染类断言跳过
        pytest.skip("系统缺中文字体，跳过渲染断言")


# ---------------------------------------------------------------- 设计解析
def test_spec_uses_translated_title_and_source_title() -> None:
    spec = cv.resolve_spec(
        _pub(creator="朱莉娅 · 尤尔丘克", translator="OpenCode"), Config(), spec_file={}
    )
    assert spec.title == ["重构意义世界"]
    assert spec.original_title == ["Reordering of Meaningful Worlds"]
    assert spec.credits == ["朱莉娅 · 尤尔丘克 著", "OpenCode 译"]
    assert spec.style == cv.STYLE == "quarto"
    assert spec.palette == "ink"
    assert spec.colors == cv.PALETTES["ink"]
    assert spec.imprint == "马加丹汉化组"


def test_spec_does_not_invent_text_from_description() -> None:
    """没有副书名就是没有：不从 description 里切句子。"""
    pub = _pub(description="这是一段很长的内容简介，不该出现在封面上。")
    spec = cv.resolve_spec(pub, Config(), spec_file={})
    assert spec.subtitle == []
    assert spec.original_subtitle == []


def test_spec_original_title_dropped_when_identical() -> None:
    pub = Publication(slug="d", meta=PublicationMeta(title="重构意义世界"))
    spec = cv.resolve_spec(pub, Config(), spec_file={})
    assert spec.title == ["重构意义世界"]
    assert spec.original_title == []  # 同一行不重复印两遍


def test_spec_file_overrides_and_flattening() -> None:
    spec = cv.resolve_spec(
        _pub(),
        Config(),
        spec_file={
            "title": "史书",
            "lead": "前皇帝约翰尼斯 · 坎塔库泽努斯",
            "series": "拜占庭历史文献集成",
            "credits": ["[东罗马] 某人 著\n[德] 另一人 校订"],
            "palette": "oxblood",
            "size": "b5",
        },
    )
    assert spec.title == ["史书"]
    assert spec.credits == ["[东罗马] 某人 著", "[德] 另一人 校订"]
    assert spec.series == ["拜占庭历史文献集成"]
    assert spec.palette == "oxblood"
    assert round(spec.width) == round(176 * 72 / 25.4)


def test_unknown_palette_style_and_size_are_explicit_errors() -> None:
    with pytest.raises(cv.CoverError, match="未知色板"):
        cv.resolve_spec(_pub(), Config(), spec_file={}, palette="chartreuse")
    with pytest.raises(cv.CoverError, match="未知开本"):
        cv.resolve_spec(_pub(), Config(), spec_file={}, size="a9")
    with pytest.raises(cv.CoverError, match="未知版式"):
        cv.resolve_spec(_pub(), Config(), spec_file={}, style="baroque")


def test_old_magadan_style_is_disabled() -> None:
    """旧版式已停用：点名 magadan 要给得出「已停用」的解释，而不是静默换版式。"""
    with pytest.raises(cv.CoverError, match="已停用"):
        cv.resolve_spec(_pub(), Config(), spec_file={}, style="magadan")
    with pytest.raises(cv.CoverError, match="已停用"):
        cv.resolve_spec(_pub(), Config(), spec_file={"style": "magadan"})


def test_legibility_floor_at_600px() -> None:
    """600px 宽的成品上，最小字号也要 ≥14px（再小的分辨率不考虑）。"""
    cfg = Config()
    page_w = cv.resolve_spec(_pub(), cfg, spec_file={}).width
    for key, frac in cv.QUARTO_TYPE.items():
        assert frac >= cv.MIN_TYPE_FRAC, key
        assert frac * cv.LEGIBILITY_REF_WIDTH_PX >= cv.LEGIBILITY_EM_PX, key
        assert frac * page_w * 600 / page_w >= 13.99, key
    # 缩放兜底不会把任何元素缩到线下
    spec = cv.resolve_spec(
        _pub(), cfg, spec_file={"title": "晚期资本主义的文化逻辑与后现代主义的起源"}
    )
    fonts = _fonts_or_skip()
    texts, _rules, _fits = cv._quarto_layout(spec, cv._Measurer(fonts), fonts, 0.81)
    assert min(item[1] for item in texts) >= cv.MIN_TYPE_FRAC * page_w


def test_missing_title_is_an_explicit_error() -> None:
    pub = Publication(slug="d", meta=PublicationMeta())
    with pytest.raises(cv.CoverError, match="没有书名"):
        cv.resolve_spec(pub, Config(), spec_file={})


def test_spec_file_contract(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    path = store.dir / cv.SPEC_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(json.dumps({"subtitle": "x", "typo_field": 1}), encoding="utf-8")
    with pytest.raises(cv.CoverError, match="未知字段"):
        cv.read_spec_file(store)

    path.write_text(json.dumps({"credits": [1, 2]}), encoding="utf-8")
    with pytest.raises(cv.CoverError, match="credits"):
        cv.read_spec_file(store)

    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(cv.CoverError, match="不可读"):
        cv.read_spec_file(store)


# ---------------------------------------------------------------- 排版
def test_render_is_deterministic() -> None:
    fonts = _fonts_or_skip()
    spec = cv.resolve_spec(_pub(), Config(), spec_file={"subtitle": "副书名"})
    first = cv.render_png(spec, fonts, dpi=100)
    assert first == cv.render_png(spec, fonts, dpi=100)
    assert first.startswith(b"\x89PNG\r\n\x1a\n")


def test_quarto_layout_proportions() -> None:
    """quarto（默认）：整幅深底、书名从 0.255H 起、责任者贴 0.878H、署名在右下。"""
    fonts = _fonts_or_skip()
    spec = cv.resolve_spec(
        _pub(creator="朱莉娅 · 尤尔丘克"),
        Config(),
        spec_file={"subtitle": "后苏联时期乌克兰对乌克兰\n民族主义者组织和乌克兰起义军的记忆"},
    )
    assert spec.style == "quarto"
    png = cv.render_png(spec, fonts, dpi=72)
    samples, w, h, n, stride = _pixels(png)
    # 整幅底面：四角都是深色（不是白底 + 色块）
    for xf, yf in ((0.5, 0.02), (0.5, 0.5), (0.97, 0.5), (0.5, 0.98)):
        row = samples[int(h * yf) * stride : int(h * yf) * stride + w * n]
        assert row[int(w * xf) * n] < 80, (xf, yf)
    # 小字号在 72dpi 下本来就淡，量测放到 144dpi，阈值 90（底面 R≈23）
    runs, _w, h2 = _ink_rows(png, x_from=0.10, x_to=0.90, light=True, dpi=144, threshold=90)
    assert runs
    title = next(run for run in runs if 0.20 < run[0] / h2 < 0.34)
    assert title[0] / h2 == pytest.approx(0.255, abs=0.012)
    credits = next(run for run in runs if 0.83 < run[0] / h2 < 0.90)
    assert credits[1] / h2 == pytest.approx(0.878, abs=0.015)
    assert runs[-1][0] / h2 == pytest.approx(0.940, abs=0.02)  # 右下署名


def test_short_title_grows_and_long_title_wraps() -> None:
    """「字少就大、字多就稳」：短书名放大到接近版心，长书名收到 0.75 倍后折行。"""
    fonts = _fonts_or_skip()
    measurer = cv._Measurer(fonts)
    page_w = cv.resolve_spec(_pub(), Config(), spec_file={}).width
    measure = page_w * (1 - 2 * cv.QUARTO_GEOM["margin"])

    def title_size(text: str) -> float:
        spec = cv.resolve_spec(
            Publication(slug="d", meta=PublicationMeta(title=text, title_translated=text)),
            Config(),
            spec_file={},
        )
        texts, _rules, _fits = cv._quarto_layout(spec, measurer, fonts, 1.0)
        return max(size for line, size, *_ in texts if line and size > 10)

    base = cv.QUARTO_TYPE["title"] * page_w
    assert title_size("史书") > base  # 短书名涨字号
    assert title_size("晚期资本主义的文化逻辑与后现代主义的起源") < base  # 长书名收字号后折行
    # 短书名也不至于撑爆版心
    assert title_size("重构意义世界") <= base * cv.QUARTO_GEOM.get("title_max", 1.45) + 1e-6
    assert measure > 0


def test_paper_palette_is_light_ground() -> None:
    """浅色版式：纸底墨字，同一套版式换色不换骨架。"""
    spec = cv.resolve_spec(_pub(), Config(), spec_file={}, palette="paper")
    field = int(spec.colors["field"].lstrip("#")[0:2], 16)
    type_c = int(spec.colors["type"].lstrip("#")[0:2], 16)
    assert field > 200 and type_c < 60  # 纸底墨字


def test_png_and_pdf_share_the_same_page_size() -> None:
    import pymupdf

    fonts = _fonts_or_skip()
    spec = cv.resolve_spec(_pub(), Config(), spec_file={})
    doc = pymupdf.open(stream=cv.render_pdf(spec, fonts), filetype="pdf")
    assert len(doc) == 1
    assert doc[0].rect.width == pytest.approx(spec.width, abs=0.5)
    assert doc[0].rect.height == pytest.approx(spec.height, abs=0.5)
    doc.close()


def test_script_font_missing_degrades_instead_of_failing(monkeypatch) -> None:
    fonts = _fonts_or_skip()
    no_script = cv.Fonts(cjk=fonts.cjk, latin=fonts.latin, script=None, missing=("script",))
    spec = cv.resolve_spec(_pub(), Config(), spec_file={})
    png = cv.render_png(spec, no_script, dpi=72)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_wrap_balances_lines_and_keeps_punctuation_off_line_start() -> None:
    fonts = _fonts_or_skip()
    measurer = cv._Measurer(fonts)
    text = "伊斯兰共和国的权力焦虑与地区秩序的重新排列"
    lines = cv.wrap(text, 60.0, 10.0, measurer)
    assert len(lines) >= 2
    assert all(not line.startswith(tuple(cv.NO_LINE_START)) for line in lines)
    assert "".join(lines) == text.replace(" ", "")


# ---------------------------------------------------------------- 工作区接线
def test_generate_registers_and_build_embeds_cover_image(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(store, title="重构意义世界", creator="朱莉娅 · 尤尔丘克", translator="OpenCode")
    record = orch.generate_cover(store)
    assert record["file"] == cv.GENERATED_REL
    assert (store.dir / cv.GENERATED_REL).is_file()
    assert (store.dir / cv.RECORD_FILE).is_file()

    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'properties="cover-image"' in opf
        assert '<meta name="cover"' in opf
        assert zf.read("OEBPS/media/cover-generated.png").startswith(b"\x89PNG")
    events = (store.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "cover_generated_used" in events


def test_build_does_not_invent_cover_without_registration(tmp_path: Path) -> None:
    """没有登记就什么都不做——「没有源封面」不等于「必须造一个封面」。"""
    store = _workspace(tmp_path)
    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        assert "cover-image" not in zf.read("OEBPS/content.opf").decode("utf-8")


def test_generated_cover_does_not_override_source_cover(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    raw = store.structured_dir / "raw" / "media"
    raw.mkdir(parents=True, exist_ok=True)
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32
    (raw / "p001.png").write_bytes(jpeg)
    (store.preprocessing_dir / "cover.json").write_text(
        json.dumps(
            {"file": "structured/raw/media/p001.png", "evidence": "第 1 页整页图，比对确认"}
        ),
        encoding="utf-8",
    )
    orch.generate_cover(store)
    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'href="media/p001.png"' in opf
        assert "cover-generated.png" not in opf


def test_metadata_change_triggers_regeneration(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(store, title="旧书名")
    first = orch.generate_cover(store)
    orch.set_meta(store, title="新书名")
    orch.build(store)
    record = json.loads((store.dir / cv.RECORD_FILE).read_text(encoding="utf-8"))
    assert record["design_digest"] != first["design_digest"]
    assert record["text"]["title"] == ["新书名"]
    events = (store.dir / "events.jsonl").read_text(encoding="utf-8")
    assert "cover_regenerated" in events


def test_remove_cover(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.generate_cover(store)
    orch.delete_cover(store)
    assert not (store.dir / cv.GENERATED_REL).exists()
    assert not (store.dir / cv.RECORD_FILE).exists()
    with pytest.raises(orch.OrchestrationError, match="没有生成封面"):
        orch.delete_cover(store)


def test_disabled_cover_refuses(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    cfg = Config()
    cfg.cover.enabled = False
    with pytest.raises(orch.OrchestrationError, match="关闭"):
        orch.generate_cover(store, config=cfg)


def test_cli_cover_json(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    orch.set_meta(store, title="重构意义世界")
    result = runner.invoke(app, ["cover", "--workspace", str(store.dir.parent), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["palette"] == "ink"
    assert payload["style"] == "quarto"
    assert payload["file"] == cv.GENERATED_REL


def test_quarto_background_has_no_white_raster_edge() -> None:
    """回归：深色底面栅格化后最外一列不得留白。"""
    fonts = _fonts_or_skip()
    spec = cv.resolve_spec(_pub(), Config(), spec_file={"subtitle": "副书名"})
    data = cv.render_image(spec, fonts, dpi=150, fmt="png")
    samples, width, height, n, stride = _pixels(data, dpi=150)

    def rgb(x: int, y: int) -> tuple[int, int, int]:
        i = y * stride + x * n
        return samples[i], samples[i + 1], samples[i + 2]

    edges = [rgb(x, 0) for x in range(0, width, 7)] + [
        rgb(x, height - 1) for x in range(0, width, 7)
    ]
    assert not any(min(pixel) > 250 for pixel in edges), "封面上下边缘出现白边"


def test_rebuild_preserves_registered_generated_cover(tmp_path: Path) -> None:
    """#71：preprocess --force 重建清空 structured/ 后，已登记封面不能丢。"""
    store = _workspace(tmp_path)
    orch.set_meta(store, title="重构意义世界", creator="作者")
    orch.generate_cover(store)
    source = store.dir / cv.GENERATED_REL
    before = source.read_bytes()

    orch.rebuild(store)
    assert source.is_file() and source.read_bytes() == before
    epub = orch.build(store)
    with zipfile.ZipFile(epub) as zf:
        assert 'properties="cover-image"' in zf.read("OEBPS/content.opf").decode("utf-8")


def test_missing_generated_cover_is_redrawn_on_build(tmp_path: Path) -> None:
    """#71：登记还在但文件缺失时必须重绘，不能静默产出无封面成品。"""
    store = _workspace(tmp_path)
    orch.set_meta(store, title="重构意义世界", creator="作者")
    orch.generate_cover(store)
    (store.dir / cv.GENERATED_REL).unlink()

    epub = orch.build(store)
    assert (store.dir / cv.GENERATED_REL).is_file()
    with zipfile.ZipFile(epub) as zf:
        assert 'properties="cover-image"' in zf.read("OEBPS/content.opf").decode("utf-8")
    assert "cover_regenerated_missing" in (store.dir / "events.jsonl").read_text(encoding="utf-8")


def test_epub_has_cover_requires_manifest_properties(tmp_path: Path) -> None:
    """#100：OPF 里的普通字符串/注释不算 cover-image。"""
    import zipfile

    from auto_epublizer.cover import epub_has_cover

    def make(path: Path, opf: str) -> Path:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")
            zf.writestr("OEBPS/content.opf", opf)
        return path

    decoy = make(
        tmp_path / "decoy.epub",
        "<package><manifest><!-- cover-image -->"
        '<item id="x" href="x.png" media-type="image/png"/></manifest></package>',
    )
    assert epub_has_cover(decoy) is False

    real = make(
        tmp_path / "real.epub",
        '<package><manifest><item id="c" href="c.png" media-type="image/png" '
        'properties="nav cover-image"/></manifest></package>',
    )
    assert epub_has_cover(real) is True


def test_cover_record_reports_physical_pixels_and_translator_credit(tmp_path: Path) -> None:
    """#100：像素口径 = 物理尺寸 × dpi；译者行进入登记文本，便于 QA 断言。"""
    store = _workspace(tmp_path)
    orch.set_meta(store, title="重构意义世界", creator="朱莉娅 · 尤尔丘克", translator="OpenCode")
    record = orch.generate_cover(store, dpi=300)
    assert record["dpi"] == 300
    assert record["size_mm"] == [148.0, 210.0]
    width, height = record["pixels"]
    # A5 @300dpi ≈ 1748×2480；渲染器按页宽取整，允许 ±2px，仍不是固定 1600×2400。
    assert abs(width - 1748) <= 2 and abs(height - 2480) <= 2
    assert "OpenCode 译" in record["text"]["credits"]
