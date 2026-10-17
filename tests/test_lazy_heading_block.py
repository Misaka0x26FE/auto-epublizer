"""回归测试：非首行的 ATX 标题必须提升为独立块（CommonMark「标题可打断段落」）。

缺陷（2026-10-08 实测）：渲染层按空行切块，源抽取与 MinerU OCR 常丢失标题前的空行
（parliamentary-socialism 全书 33 处，如题词「…Ramsay MacDonald, 1909」下一行紧跟
`## 1. THE LIBERAL CONNECTION`）。标题遂成为懒续行被整体塞进 `<p>`，读者直接看到
字面 `## 1. 与自由党的联系`——G0 标题计数两侧相等故不报，epubcheck 也不管正文渲染，
**检测层与渲染层同时漏**。

同时守住两条不变量：
1. `markdown_to_xhtml` 与 `subheading_anchors` 共用 `_iter_blocks`，nav 锚点不悬空；
2. 围栏代码块内的 `#` 是内容不是标题，不得切分。
"""

from auto_epublizer.build.html import markdown_to_xhtml, subheading_anchors


def test_lazy_heading_is_promoted_to_h2():
    md = "「……」——麦克唐纳，1909 年\n## 1. 与自由党的联系\n\n下议院中独立的工党代表权。\n"
    out = markdown_to_xhtml(md, unit_id="ch01")
    assert "<h2" in out and "与自由党的联系" in out
    assert "## 1. 与自由党的联系" not in out, "字面 ## 不得印给读者"
    # 题词仍是独立段落，标题不再混在其中
    assert "麦克唐纳，1909 年</p>" in out


def test_lazy_heading_does_not_swallow_following_text():
    """标题之后的正文须是独立 <p>，不能被当作标题块的首行（那会让正文进 <h2>）。"""
    md = "题词。\n## 2. 工党左翼\n下议院中独立的工党代表权。\n"
    out = markdown_to_xhtml(md, unit_id="ch01")
    assert "<h2" in out
    assert "工党左翼</h2>" in out
    assert "下议院中独立的工党代表权。</p>" in out


def test_nav_anchors_match_rendered_ids():
    """切分后 nav 锚点与渲染 id 必须一一对应（目录链接不悬空）。"""
    md = "题词。\n## 1. 与自由党的联系\n\n正文。\n"
    anchors = subheading_anchors(md, "ch01")
    assert [a["anchor"] for a in anchors] == ["ch01-h1"]
    assert anchors[0]["title"] == "1. 与自由党的联系"
    out = markdown_to_xhtml(md, unit_id="ch01")
    assert 'id="ch01-h1"' in out


def test_fenced_code_block_is_not_split():
    md = "题词。\n## 1. 标题\n\n```\n# 这是代码注释\n## 不是标题\n```\n"
    out = markdown_to_xhtml(md, unit_id="ch01")
    assert "## 1. 标题" not in out
    assert "<h2" in out


def test_normal_block_heading_unchanged():
    """块首标题的既有行为不变（防过度切分回归）。"""
    out = markdown_to_xhtml("## 1. 甲\n正文。\n", unit_id="ch01")
    assert "1. 甲</h2>" in out and "正文。</p>" in out


def test_consecutive_headings_are_separated():
    """连续标题行 `## A` / `### B`：`### B` 不得被当作 `## A` 之后的正文塞进 <p>。

    缺陷实测：matla-al-sadayn-1 3 处（`## 回历 755 年之事` 紧接 `### 按语`）、
    nazi-crimes-occupied-ussr-1 1 处（`### 200. …` 紧接 `### 201. …`）。
    首版修复只在「非块首」切分，连续标题仍漏，故此处单列回归。
    """
    out = markdown_to_xhtml("## 回历 755 年之事\n### 按语\n\n正文。\n", unit_id="ch05")
    assert "回历 755 年之事</h2>" in out
    assert "按语</h3>" in out
    assert "按语</p>" not in out


def test_heading_inline_attr_empty_brackets_removed():
    """`### **# 1**[]{#d1}`：剥 id 时须连同其前的空 `[]` 一起吃掉，否则读者看到 `[]`。"""
    from auto_epublizer.build.html import _split_heading_id, plain_label

    text, hid = _split_heading_id("**# 1**[]{#d1}")
    assert hid == "d1"
    assert text == "**# 1**"
    assert plain_label("**# 1**[]{#d1}") == "# 1"


def test_anchor_span_accepts_missing_hash():
    """`[]{GBS.0014.05}`（抽取丢了井号）→ 空锚点，不留字面 `[]`。"""
    out = markdown_to_xhtml("正文[]{GBS.0014.05}后续。\n", unit_id="ch02")
    assert 'id="GBS.0014.05"' in out
    assert "[]" not in out


def test_anchor_span_still_rejects_spaces():
    """校勘标记 `[]{#word illegible}` 含空格，**不得**被当成锚点吞掉。"""
    out = markdown_to_xhtml("某词[]{#word illegible}。\n", unit_id="ch05")
    assert "word illegible" in out
    assert 'id="word illegible"' not in out


def test_anchor_span_allows_space_before_brace():
    """抽取噪声 `[] {#GBS.0053.02}`（`[]` 与 `{` 间有空格）也要认成锚点。"""
    out = markdown_to_xhtml("承诺。[] {#GBS.0053.02}这当然\n", unit_id="ch03")
    assert 'id="GBS.0053.02"' in out
    assert "[]" not in out


def test_anchor_space_does_not_span_lines():
    """`[ \\t]*` 而非 `\\s*`：不得跨行把下一段的花括号一起吞掉。"""
    out = markdown_to_xhtml("正文[]{#a}\n\n下一段 {attrs} 结束\n", unit_id="ch03")
    assert 'id="a"' in out
    assert "{attrs}" in out


def test_plain_label_strips_spaced_anchor():
    from auto_epublizer.build.html import plain_label

    assert plain_label("**# 1**[] {#d1}") == "# 1"


def test_empty_attr_block_removed():
    """`{[]}[]{#id}`：锚点取出后，空属性壳 `{[]}` 不得以字面印给读者。"""
    out = markdown_to_xhtml("前提。{[]}[]{#GBS.0682.04}\n", unit_id="ch11")
    assert 'id="GBS.0682.04"' in out
    assert "{[]}" not in out
    assert "[]" not in out


def test_plain_label_drops_empty_attr_block():
    from auto_epublizer.build.html import plain_label

    assert plain_label("**# 1**{[]}[]{#d1}") == "# 1"
