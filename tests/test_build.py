"""build 测试：XHTML 渲染、确定性 EPUB 写入、ZIP 结构验证。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from auto_common.workspace import Publication, PublicationMeta, Unit
from auto_epublizer.build import build_epub, theme_css
from auto_epublizer.build.html import (
    FootnoteState,
    markdown_to_xhtml,
    render_bilingual_document,
    render_document,
    slug_file,
)


def test_markdown_to_xhtml() -> None:
    out = markdown_to_xhtml("# 标题\n\n第一段。\n\n第二段。\n")
    assert "<h1>标题</h1>" in out
    assert "<p>第一段。</p>" in out
    assert "<p>第二段。</p>" in out


def test_markdown_to_xhtml_escapes() -> None:
    out = markdown_to_xhtml("<script>alert(1)</script>\n")
    assert "&lt;script&gt;" in out


def test_render_document() -> None:
    html = render_document("T", "para", lang="zh-CN")
    assert 'xml:lang="zh-CN"' in html
    assert "<title>T</title>" in html


def test_slug_file() -> None:
    assert slug_file("ch01") == "ch01"
    assert slug_file("front-titlepage") == "front-titlepage"


def test_render_bilingual_document() -> None:
    rows = [
        {"seq": 1, "src": "Hello.", "tgt": "你好。"},
        {"seq": 2, "src": "World.", "tgt": "世界。"},
    ]
    html = render_bilingual_document(
        "T", rows, lang_src="en", lang_tgt="zh-CN", order="target_first"
    )
    assert 'xml:lang="zh-CN"' in html
    assert 'class="src"' in html
    assert 'class="tgt"' in html
    assert html.index("你好。") < html.index("Hello.")
    # source_first 顺序相反
    html2 = render_bilingual_document(
        "T", rows, lang_src="en", lang_tgt="zh-CN", order="source_first"
    )
    assert html2.index("Hello.") < html2.index("你好。")


def _pub() -> Publication:
    return Publication(
        slug="book",
        meta=PublicationMeta(title="测试书", creator="作者", target_language="zh-CN"),
        units=[Unit(id="ch01", kind="chapter", title="第一章")],
    )


def test_build_epub_structure(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
    ]
    content_files = [
        ("ch01.xhtml", render_document("第一章", "# 第一章\n\n正文。\n", lang="zh-CN"))
    ]
    out = build_epub(
        pub,
        entries,
        content_files,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "book.epub",
    )
    assert out.is_file()
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype"
        assert zf.read("mimetype") == b"application/epub+zip"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        for expected in (
            "META-INF/container.xml",
            "OEBPS/content.opf",
            "OEBPS/nav.xhtml",
            "OEBPS/toc.ncx",
            "OEBPS/landmarks.xhtml",
            "OEBPS/ch01.xhtml",
        ):
            assert expected in names, expected
        container = zf.read("META-INF/container.xml").decode("utf-8")
        assert "OEBPS/content.opf" in container
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "dc:title" in opf
        assert "dcterms:modified" in opf
        assert 'media-type="application/xhtml+xml"' in opf
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        assert "ch01.xhtml" in nav


def test_build_epub_deterministic(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "ch02", "region": "body", "title": "第二章"},
    ]
    content_files = [
        ("ch01.xhtml", render_document("第一章", "para1", lang="zh-CN")),
        ("ch02.xhtml", render_document("第二章", "para2", lang="zh-CN")),
    ]
    args = dict(lang="zh-CN", modified="2026-01-01T00:00:00Z")
    out1 = build_epub(pub, entries, content_files, out_path=tmp_path / "a.epub", **args)
    out2 = build_epub(pub, entries, content_files, out_path=tmp_path / "b.epub", **args)
    assert out1.read_bytes() == out2.read_bytes()


def test_build_epub_frontmatter_landmarks(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "front-preface", "region": "frontmatter", "title": "前言"},
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "back-index", "region": "backmatter", "title": "索引"},
    ]
    content_files = [
        (f"{e['id']}.xhtml", render_document(e["title"], "正文。\n", lang="zh-CN")) for e in entries
    ]
    out = build_epub(
        pub,
        entries,
        content_files,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "b.epub",
    )
    with zipfile.ZipFile(out) as zf:
        lm = zf.read("OEBPS/landmarks.xhtml").decode("utf-8")
        assert 'epub:type="frontmatter"' in lm
        assert 'epub:type="bodymatter"' in lm
        assert 'epub:type="backmatter"' in lm


def test_build_epub_ncx(tmp_path: Path) -> None:
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "ch02", "region": "body", "title": "第二章"},
    ]
    content = [("ch01.xhtml", render_document("第一章", "正文一。\n", lang="zh-CN"))]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "c.epub",
    )
    with zipfile.ZipFile(out) as zf:
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
        assert "navPoint" in ncx
        assert "playOrder" in ncx
        # 只引用实际生成的内容文档（ch02 未生成，不得出现在 NCX）
        assert "ch02.xhtml" not in ncx
        assert "ch01.xhtml" in ncx


def test_build_epub_escapes_xml_metadata(tmp_path: Path) -> None:
    """书名/作者含 XML 特殊字符时，所有 XML 文档必须仍可解析（P2 回归）。"""
    import xml.etree.ElementTree as ET

    pub = Publication(
        slug="book",
        meta=PublicationMeta(title="War & Peace <笔记>", creator="A & B", target_language="zh-CN"),
        units=[Unit(id="ch01", kind="chapter", title="第一章")],
    )
    entries = [{"id": "ch01", "region": "body", "title": "War & Peace <续>"}]
    out = build_epub(
        pub,
        entries,
        [],
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "esc.epub",
    )
    with zipfile.ZipFile(out) as zf:
        for name in ("OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/toc.ncx"):
            ET.fromstring(zf.read(name).decode("utf-8"))  # 不抛 ParseError 即合法 XML


def test_build_epub_dc_language_uses_lang_arg(tmp_path: Path) -> None:
    """convert 纯转换路径：dc:language 必须用传入的源语言，而非 target_language（P2 回归）。"""
    import xml.etree.ElementTree as ET

    pub = Publication(
        slug="book",
        meta=PublicationMeta(title="English Book", language="en", target_language="zh-CN"),
        units=[Unit(id="ch01", kind="chapter", title="Chapter I")],
    )
    out = build_epub(
        pub,
        [{"id": "ch01", "region": "body", "title": "Chapter I"}],
        [],
        lang="en",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "en.epub",
    )
    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        root = ET.fromstring(opf)
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        lang_el = root.find(".//dc:language", ns)
        assert lang_el is not None and lang_el.text == "en"


def test_collect_media_rewrites_and_collects(tmp_path: Path) -> None:
    """图片引用统一改写为 media/ 路径并收集字节（豆包实测 P5/P10 回归）。"""
    from auto_epublizer.build import collect_media

    media_root = tmp_path / "raw" / "media"
    media_root.mkdir(parents=True)
    (media_root / "x.png").write_bytes(b"PNGDATA")

    md = "前文\n\n![插图](raw/media/x.png)\n\n后文"
    rewritten, files = collect_media(md, media_root)
    assert "![插图](media/x.png)" in rewritten
    assert files == [("media/x.png", b"PNGDATA")]

    # pandoc 孤立图片占位语法 → 标准引用
    md2 = '[alt]{.image .placeholder original-image-src="raw/media/x.png"}'
    rewritten2, files2 = collect_media(md2, media_root)
    assert "![alt](media/x.png)" in rewritten2
    assert files2 == [("media/x.png", b"PNGDATA")]

    # HTML <img>（含 figure/a 包裹）→ 标准引用
    md3 = '<figure><a href="x"><img src="raw/media/x.png"/></a></figure>'
    rewritten3, files3 = collect_media(md3, media_root)
    assert "![](media/x.png)" in rewritten3

    # 找不到的文件：引用被移除，避免悬空
    rewritten4, files4 = collect_media("![nope](raw/media/missing.png)", media_root)
    assert "![" not in rewritten4
    assert files4 == []


def test_collect_media_subdir_and_paren_paths(tmp_path: Path) -> None:
    """子目录同名文件不得错配；含括号文件名不截断（本仓检测回归）。"""
    from auto_epublizer.build import collect_media

    media_root = tmp_path / "raw" / "media"
    media_root.mkdir(parents=True)
    (media_root / "x.png").write_bytes(b"TOP")
    (media_root / "sub").mkdir()
    (media_root / "sub" / "x.png").write_bytes(b"SUB")
    (media_root / "a (1).png").write_bytes(b"PAREN")

    # 1. 子目录引用：包内路径保留 sub/，字节取 sub 下的
    out, files = collect_media("![x](sub/x.png)", media_root)
    assert "![x](media/sub/x.png)" in out
    assert ("media/sub/x.png", b"SUB") in files
    # 顶层引用不受影响（同名不冲突）
    out2, files2 = collect_media("![x](x.png)", media_root)
    assert ("media/x.png", b"TOP") in files2

    # 2. 括号文件名：引用不丢、字节收集到、href 百分号编码
    out3, files3 = collect_media("![x](a (1).png)", media_root)
    assert "![](media/a%20%281%29.png)" in out3 or "![x](media/a%20%281%29.png)" in out3
    assert ("media/a (1).png", b"PAREN") in files3


def test_markdown_to_xhtml_renders_img_and_blocks_dangerous_urls() -> None:
    """media/ 图片渲染为 <img>（限宽）；独立图段 alt 非空 → figure+figcaption（P1）。"""
    out = markdown_to_xhtml("![插图](media/x.png)\n")
    assert '<img src="media/x.png" alt="插图"' in out
    assert "max-width:100%" in out  # 限宽防溢出
    assert '<figure class="imgfig">' in out and "<figcaption>插图</figcaption>" in out

    # alt 为空的独立图段：回退 p.imgp（无图注可渲染）
    out_empty_alt = markdown_to_xhtml("![](media/x.png)\n")
    assert '<p class="imgp">' in out_empty_alt and "<figcaption>" not in out_empty_alt

    out2 = markdown_to_xhtml("[点我](javascript:alert(1))\n")
    assert "<a " not in out2
    assert "点我" in out2


def test_markdown_to_xhtml_cleans_pandoc_markers() -> None:
    """清理 pandoc/MediaWiki 排版残留（豆包实测 P13/P14 回归）。"""
    md = "::: {.thumb}\n\n插图说明文字。\n\n::: gallerytext\n\n:::\n\n\\\n"
    out = markdown_to_xhtml(md)
    assert "::" not in out
    assert "插图说明文字。" in out
    assert "\\" not in out

    # MediaWiki 引用标记 \>> / \> → ——（中文小说场景提示排版）
    out2 = markdown_to_xhtml("\\>\\> 三天后，伦敦。\n")
    assert "——" in out2
    assert "&gt;" not in out2


def test_render_document_links_stylesheet() -> None:
    """内容文档引用内置 style.css（豆包实测 P16 回归）。"""
    out = render_document("T", "正文。", lang="zh-CN")
    assert '<link rel="stylesheet" type="text/css" href="style.css"/>' in out


def test_build_epub_embeds_media_files(tmp_path: Path) -> None:
    """media_files 参数把图片字节写入包内并在 manifest 登记。"""
    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content = [("ch01.xhtml", render_document("第一章", "![图](media/x.png)\n", lang="zh-CN"))]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "m.epub",
        media_files=[("media/x.png", b"PNGDATA")],
    )
    with zipfile.ZipFile(out) as zf:
        assert zf.read("OEBPS/media/x.png") == b"PNGDATA"
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "media/x.png" in opf
        assert "image/png" in opf


def test_build_epub_embeds_stylesheet(tmp_path: Path) -> None:
    """内置 style.css 入包 + manifest 注册；呈现层只留功能性样式（epub-template-spec §4）。"""
    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content = [("ch01.xhtml", render_document("第一章", "正文。\n", lang="zh-CN"))]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "s.epub",
    )
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "OEBPS/style.css" in names
        css = zf.read("OEBPS/style.css").decode("utf-8")
        # 功能性规则保留：图片只缩不放大、图片段居中
        assert "max-width: 100%" in css and "p.imgp" in css
        # 呈现层 + 主题层边界：泛化族名允许；具体字体名/字号/颜色禁止（阅读器领地）
        assert "font-family: serif" in css  # 默认 standard 主题
        for banned in ("Georgia", "Noto Serif", "font-size", "color:"):
            assert banned not in css, f"非功能性样式残留：{banned}"
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'href="style.css"' in opf and "text/css" in opf


def test_theme_css_variants(tmp_path: Path) -> None:
    """主题机制：三套预置主题只控排版微调；未知主题报错（epub-template-spec §5）。"""
    pub = _pub()
    entries = [{"id": "ch01", "region": "body", "title": "第一章"}]
    content = [("ch01.xhtml", render_document("第一章", "正文。\n", lang="zh-CN"))]
    css_by_theme = {}
    for theme in ("standard", "compact", "spacious"):
        out = build_epub(
            pub,
            entries,
            content,
            lang="zh-CN",
            modified="2026-01-01T00:00:00Z",
            out_path=tmp_path / f"{theme}.epub",
            theme=theme,
        )
        with zipfile.ZipFile(out) as zf:
            css_by_theme[theme] = zf.read("OEBPS/style.css").decode("utf-8")
    assert "line-height: 1.7" in css_by_theme["standard"]
    assert "font-family: sans-serif" in css_by_theme["compact"]
    assert "line-height: 2.0" in css_by_theme["spacious"]
    # 主题不引入具体字体名/颜色/字号
    for css in css_by_theme.values():
        assert "font-size" not in css and "color:" not in css and '"' not in css
    with pytest.raises(ValueError, match="未知主题"):
        theme_css("nope")


def test_cover_image_and_linear_no(tmp_path: Path) -> None:
    """封面：cover-image 属性 + <meta name=cover> + cover 单元 spine linear=no。"""
    pub = _pub()
    entries = [
        {"id": "cover", "kind": "cover", "region": "cover", "title": "封面"},
        {"id": "ch01", "kind": "chapter", "region": "body", "title": "第一章"},
    ]
    content = [
        ("cover.xhtml", render_document("封面", "![封面](media/cover.png)\n", lang="zh-CN")),
        ("ch01.xhtml", render_document("第一章", "正文。", lang="zh-CN")),
    ]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "c.epub",
        media_files=[("media/cover.png", b"PNGDATA")],
        cover_media="media/cover.png",
    )
    with zipfile.ZipFile(out) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
    assert 'properties="cover-image"' in opf
    assert '<meta name="cover" content="media/cover.png"/>' in opf
    assert '<itemref idref="cover.xhtml" linear="no"/>' in opf
    assert '<itemref idref="ch01.xhtml"/>' in opf


def test_build_epub_ncx_no_dangling_refs(tmp_path: Path) -> None:
    """被跳过的空壳单元不得被 NCX/landmarks 引用（豆包实测 P9 引发的悬空引用回归）。"""
    pub = _pub()
    # 2 个 entries，但只有 ch01 生成了内容文件（ch02 是被 _skip_empty_unit 跳过的空壳）
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章"},
        {"id": "ch02", "region": "body", "title": "空壳"},
    ]
    content = [("ch01.xhtml", render_document("第一章", "正文。\n", lang="zh-CN"))]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "d.epub",
    )
    with zipfile.ZipFile(out) as zf:
        assert "OEBPS/ch02.xhtml" not in zf.namelist()
        for doc in ("OEBPS/toc.ncx", "OEBPS/landmarks.xhtml", "OEBPS/nav.xhtml"):
            text = zf.read(doc).decode("utf-8")
            assert "ch02.xhtml" not in text, f"{doc} 悬空引用 ch02.xhtml"


def test_nested_nav_and_ncx_hierarchy(tmp_path: Path) -> None:
    """目录层级：源文 level 序列 → nav 嵌套 <ol> + NCX 嵌套 navPoint + dtb:depth（P0）。"""
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "第一章", "level": 1},
        {"id": "ch02", "region": "body", "title": "第一节", "level": 2},
        {"id": "ch03", "region": "body", "title": "第二节", "level": 2},
        {"id": "ch04", "region": "body", "title": "第二章", "level": 1},
    ]
    content = [
        (f"{e['id']}.xhtml", render_document(e["title"], "正文。", lang="zh-CN")) for e in entries
    ]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "n.epub",
    )
    with zipfile.ZipFile(out) as zf:
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
    # ch02/ch03 嵌套在 ch01 的 li 内层 <ol>（首个 </ol> 即内层闭合）；ch04 回到外层
    inner = nav.split('<a href="ch01.xhtml">')[1].split("</ol>")[0]
    assert "ch02.xhtml" in inner and "ch03.xhtml" in inner and "ch04.xhtml" not in inner
    assert nav.count("<ol>") == 2
    assert "dtb:depth" in ncx and 'content="2"' in ncx


def test_flat_toc_for_flat_source(tmp_path: Path) -> None:
    """平级源（无 level 信息，如 PDF 单元）目录保持扁平、dtb:depth=1。"""
    pub = _pub()
    entries = [
        {"id": "ch01", "region": "body", "title": "甲"},
        {"id": "ch02", "region": "body", "title": "乙"},
    ]
    content = [
        (f"{e['id']}.xhtml", render_document(e["title"], "正文。", lang="zh-CN")) for e in entries
    ]
    out = build_epub(
        pub,
        entries,
        content,
        lang="zh-CN",
        modified="2026-01-01T00:00:00Z",
        out_path=tmp_path / "f.epub",
    )
    with zipfile.ZipFile(out) as zf:
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
    assert nav.count("<ol>") == 1
    assert 'dtb:depth" content="1"' in ncx


def test_footnote_semantics_global_numbering() -> None:
    """脚注语义化：noteref/footnote + 跨单元全局连续编号 + 双向跳转（epub-template-spec §6）。"""
    state = FootnoteState()
    d1 = render_document(
        "C1", "第一句[^1]。\n\n[^1]: 注甲", lang="zh-CN", unit_id="ch01", fn_state=state
    )
    d2 = render_document(
        "C2", "第二句[^1]。\n\n[^1]: 注乙", lang="zh-CN", unit_id="ch02", fn_state=state
    )
    # 章内：noteref → fn-1；章末 aside(footnote) 带 id 与回链
    assert 'epub:type="noteref"' in d1 and 'href="#fn-1"' in d1
    assert 'epub:type="footnote"' in d1 and 'id="fn-1"' in d1 and 'href="#ref-1"' in d1
    # 跨单元全局连续：ch02 的 [^1] 是全局第 2 条
    assert 'href="#fn-2"' in d2 and 'id="fn-2"' in d2 and 'href="#ref-2"' in d2
    # 字面标记不得残留
    assert "[^1]" not in d1 and "[^1]" not in d2


def test_markdown_semantic_tags() -> None:
    """语义标签保留（epub-template-spec P2）：blockquote/诗行块/ul/ol。"""
    md = "> 引用第一行。\n\n| 诗行一\n| 诗行二\n\n- 甲\n- 乙\n\n1. 第一\n2. 第二\n"
    out = markdown_to_xhtml(md)
    assert "<blockquote><p>引用第一行。</p></blockquote>" in out
    assert '<p class="verse">诗行一<br/>诗行二</p>' in out
    assert "<ul><li>甲</li><li>乙</li></ul>" in out
    assert "<ol><li>第一</li><li>第二</li></ol>" in out
