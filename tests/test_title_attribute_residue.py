"""回归测试：`<title>` 不得泄漏 pandoc 行内属性块。

缺陷（2026-10-06 实测）：`_page()` 用 `escape(title)` 直接输出 `<title>`，
而单元 md 的 h1 常带 `{#calibre_toc_N}` 之类属性块 → 读者在阅读器标签页看到字面属性。
受影响：Thiriart 22 处、fierce-enigmas 17 处（epubcheck 不报，属盲区）。

同时守住「属性块在 h1 上仍要保留为 id」——目录链接依赖那些 id。
"""

from auto_epublizer.build.html import plain_label, render_document


def test_title_strips_inline_attributes():
    md = "# Dedication {#calibre_toc_2}\n\n正文。\n"
    out = render_document("Dedication {#calibre_toc_2}", md, lang="zh-CN")
    assert "<title>Dedication</title>" in out
    assert "{#calibre_toc_2}" not in out.split("</head>")[0]


def test_title_strips_link_and_emphasis():
    out = render_document("**1** [Fortune](ch03.xhtml)", "# x\n", lang="zh-CN")
    assert "<title>1 Fortune</title>" in out


def test_heading_keeps_its_id():
    """标题上的属性块必须照常提取为 id —— 目录链接依赖它。"""
    md = "# Notes {#I3QM3-abc}\n\n正文。\n"
    out = render_document("Notes {#I3QM3-abc}", md, lang="zh-CN")
    assert 'id="I3QM3-abc"' in out  # h1 上保留
    assert "<title>Notes</title>" in out  # title 上已清理


def test_plain_label_unchanged():
    assert plain_label("A {#x}") == "A"
