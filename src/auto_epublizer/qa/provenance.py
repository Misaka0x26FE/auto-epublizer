"""后处理溯源审计（零 token、离线、确定性）。

postprocessing-spec §2/§3 的实现，四类检查全部只出信号不出裁决：

- 三边对账：structured ↔ translation ↔ EPUB spine（E_UNIT_MISSING / E_UNIT_ORDER）
- 媒体溯源：源文图片引用 vs 译文（数量与相对顺序，E_MEDIA_LOST / E_MEDIA_ORDER）
- 逐段覆盖率：structured 正文段落都能在 align 的 src 侧找到 → ``provenance_coverage``
  （无翻译产物时为 None——convert 路径不适用该门）
- 目录层级：EPUB nav 嵌套深度 vs 源文 level 序列（按 nav_depth 投影后对账；
  E_TOC_FLAT / W_TOC_DEPTH）
"""

from __future__ import annotations

import math
import posixpath
import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from auto_translator.review.fidelity import content_blocks as _paragraphs
from auto_translator.review.fidelity import norm_text as _norm
from auto_translator.review.g0 import md_align_drift
from auto_translator.translation.align import read_align

from ..build import nav_toc_entries, slug_file, toc_depths
from ..ingest.inserts import read_inserts
from ..structure import skip_empty_unit

# 图片引用三种形态：pandoc 占位（original-image-src）、HTML <img>、标准 markdown
_PLACEHOLDER_IMG = re.compile(r'original-image-src="([^"]+)"')
_HTML_IMG = re.compile(r'<img\b[^>]*?src="([^"]+)"', re.IGNORECASE)
_MD_IMG = re.compile(r"!\[[^\]]*\]\(([^()]+)\)")
_EXTERNAL = re.compile(r"^(https?:|data:)", re.IGNORECASE)


@dataclass
class ProvenanceResult:
    """溯源审计结果（postprocessing-spec §3 数据契约）。"""

    units_total: int = 0
    units_missing: list[str] = field(default_factory=list)
    units_unexpected: list[str] = field(default_factory=list)
    units_order_ok: bool = True
    coverage: float | None = None
    coverage_missing: list[str] = field(default_factory=list)  # "<unit>:<段落序>"
    media_lost: list[str] = field(default_factory=list)  # "<unit>:<basename>"
    media_order_violations: list[str] = field(default_factory=list)
    toc_depths_expected: list[int] = field(default_factory=list)
    toc_depths_nav: list[int] = field(default_factory=list)
    toc_flat: bool = False
    toc_depth_mismatch: bool = False
    # 目录深度投影：被 nav_depth 剔除（或封面）而不进目录的 spine 文档名，
    # 供 audit_epub 豁免 E_TOC_COVERAGE（内容仍在 spine 阅读顺序，非缺失）
    nav_exempt: list[str] = field(default_factory=list)
    # md↔align 全文一致性违例（交付审计 S1.1：md 是 build 输入、align 是校验基准）
    align_md_drift: list[str] = field(default_factory=list)
    # EPUB 呈现对账（交付审计 S1.2：md 引用/定义 ↔ 成品实际包含）
    epub_media_missing: list[str] = field(default_factory=list)  # "unit:图片名"
    epub_footnotes_missing: list[str] = field(default_factory=list)  # "unit（md N / EPUB M）"
    epub_coverage: float | None = None  # 段落探针覆盖率（无探针为 None）
    epub_coverage_missing: list[str] = field(default_factory=list)  # "unit:段序"
    # 插入内容（插图/表格/公式）溯源（pdf-content-spec §9）
    inserts_total: int = 0
    inserts_missing_files: int = 0
    inserts_no_desc: int = 0
    inserts_no_latex: int = 0
    findings: list[dict[str, str]] = field(default_factory=list)

    def add(self, level: str, code: str, message: str) -> None:
        self.findings.append({"level": level, "code": code, "message": message})

    @property
    def ok(self) -> bool:
        """无 error 级发现即通过（warning 不阻断）。"""
        return not any(f["level"] == "error" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _img_refs(md_text: str) -> list[str]:
    """提取 md 全部图片引用的 basename（unquote 后；外链跳过）。"""
    refs: list[str] = []
    for pattern in (_PLACEHOLDER_IMG, _HTML_IMG, _MD_IMG):
        for m in pattern.finditer(md_text or ""):
            src = m.group(1).strip().replace("\\", "/")
            if not src or _EXTERNAL.match(src):
                continue
            refs.append(unquote(Path(src).name))
    return refs


def _spine_docs(zf: zipfile.ZipFile) -> list[str]:
    """按 OPF spine 顺序解析内容文档 href（解析失败返回空）。"""
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8")
        m = re.search(r'full-path="([^"]+)"', container)
        if not m:
            return []
        opf = zf.read(m.group(1)).decode("utf-8")
    except KeyError:
        return []
    id2href: dict[str, str] = {}
    for item in re.findall(r"<item\b[^>]*>", opf):
        mid = re.search(r'\bid="([^"]+)"', item)
        mhref = re.search(r'\bhref="([^"]+)"', item)
        if mid and mhref:
            id2href[mid.group(1)] = mhref.group(1)
    spine: list[str] = []
    for ref in re.findall(r'<itemref[^>]+idref="([^"]+)"', opf):
        href = id2href.get(ref)
        if href:
            spine.append(href)
    return spine


def _opf_dir(zf: zipfile.ZipFile) -> str:
    """OPF 所在目录（zip 内路径；根目录返回空串）。"""
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8")
        m = re.search(r'full-path="([^"]+)"', container)
    except KeyError:
        return ""
    return posixpath.dirname(m.group(1)) if m else ""


def _strip_tags(html: str) -> str:
    """剥 XHTML 标签取 body 文本（实体原样保留；md/EPUB 两侧同函数保证可比较）。"""
    body = re.search(r"<body[^>]*>(.*?)</body>", html or "", re.DOTALL)
    inner = body.group(1) if body else (html or "")
    return re.sub(r"<[^>]+>", "", inner)


def _probe_missing(md_text: str, doc_text_norm: str) -> tuple[list[str], int]:
    """EPUB 正文段落探针：md 每段（用 build 同款渲染器渲染）应出现在成品文档中。

    与 build 共用 ``markdown_to_xhtml``，变换（标记清理/内联/表格/verse）天然一致；
    跳过标题行与脚注定义块（各有专责校验）。返回（未命中段落头列表, 探针段总数）。
    """
    from ..build.html import markdown_to_xhtml

    missing: list[str] = []
    total = 0
    for block in re.split(r"\n\s*\n", (md_text or "").strip("\n")):
        stripped = block.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("[^"):
            continue
        rendered = _strip_tags(markdown_to_xhtml(block))
        rendered = re.sub(r"\[\^[^\]]+\]", "", rendered)  # build 会替换为 [N] 上标
        probe = re.sub(r"\s+", "", rendered)
        if not probe:
            continue
        total += 1
        if probe not in doc_text_norm:
            missing.append(stripped[:40])
    return missing, total


def _nav_declared_depth(zf: zipfile.ZipFile) -> int | None:
    """读 nav.xhtml head 的 ``<meta name="nav-depth" content="K">`` 投影深度声明。

    构建期由 `_render_nav` 写入；以此为准可避免「build --nav-depth N 后 qa 用
    默认配置」造成的投影/豁免错位（旧书或外部工具产物无声明 → None 走兜底）。
    """
    navs = [n for n in zf.namelist() if n.endswith("nav.xhtml")]
    if not navs:
        return None
    html = zf.read(navs[0]).decode("utf-8")
    m = re.search(r'<meta\s+name="nav-depth"\s+content="(\d+)"', html)
    if not m:
        return None
    depth = int(m.group(1))
    return depth if 1 <= depth <= 6 else None


def _nav_depths(zf: zipfile.ZipFile) -> list[int]:
    """解析 nav.xhtml toc 区的 <li> 嵌套深度序列（无 nav 返回空）。"""
    navs = [n for n in zf.namelist() if n.endswith("nav.xhtml")]
    if not navs:
        return []
    html = zf.read(navs[0]).decode("utf-8")
    m = re.search(r'<nav[^>]+epub:type="toc"[^>]*>(.*?)</nav>', html, re.DOTALL)
    if not m:
        m = re.search(r"<nav\b[^>]*>(.*?)</nav>", html, re.DOTALL)
    if not m:
        return []
    depths: list[int] = []
    ol_depth = 0
    for tok in re.finditer(r"<ol\b|</ol>|<li\b", m.group(1)):
        t = tok.group(0)
        if t.startswith("<ol"):
            ol_depth += 1
        elif t == "</ol>":
            ol_depth = max(ol_depth - 1, 0)
        else:
            depths.append(max(ol_depth, 1))
    return depths


def _opf_has_cover(zf: zipfile.ZipFile) -> bool:
    """OPF 是否声明了 cover-image 属性（封面对账用）。"""
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8")
        m = re.search(r'full-path="([^"]+)"', container)
        if not m:
            return False
        return 'properties="cover-image"' in zf.read(m.group(1)).decode("utf-8")
    except KeyError:
        return False


def _audit_inserts(result: ProvenanceResult, structured_dir: Path) -> None:
    """插入内容溯源审计（raw/inserts/<id>.json 存在时；pdf-content-spec §9）。

    error：文件缺失 / source 非法（页号非正整数、bbox 非 4 个有限数）；
    warning：agent 未补 content_desc / formula 未手写 latex。
    """
    records = read_inserts(structured_dir / "raw")
    if not records:
        return
    result.inserts_total = len(records)
    raw_dir = structured_dir / "raw"
    for r in records:
        if r.file and not (raw_dir / r.file).is_file():
            result.inserts_missing_files += 1
            result.add("error", "E_INSERT_MISSING_FILE", f"插入内容文件缺失：{r.id}（{r.file}）")
        page = r.source.page
        bbox = r.source.bbox
        bad_source = not isinstance(page, int) or isinstance(page, bool) or page < 1
        if not bad_source and bbox is not None:
            bad_source = len(bbox) != 4 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
                for v in bbox
            )
        if bad_source:
            result.add("error", "E_INSERT_BAD_SOURCE", f"插入内容 source 非法：{r.id}")
        if not (r.content_desc or "").strip():
            result.inserts_no_desc += 1
            result.add("warning", "W_INSERT_NO_DESC", f"插入内容缺 agent 描述：{r.id}")
        if r.type == "formula" and not (r.latex or "").strip():
            result.inserts_no_latex += 1
            result.add("warning", "W_INSERT_NO_LATEX", f"公式缺 agent 手写 LaTeX：{r.id}")


def audit_provenance(
    store: Any,
    entries: list[dict[str, Any]],
    epub_path: str | Path,
    *,
    prefer_translation: bool = True,
    nav_depth: int = 3,
) -> ProvenanceResult:
    """对成品 EPUB 执行溯源审计（构建期跳过逻辑与本函数期望集保持一致）。

    ``prefer_translation`` 与 _render_and_pack 语义一致：译文存在时以译文为
    构建/审计基准（媒体对账才有意义），否则源↔源恒等跳过媒体检查。
    ``nav_depth`` 与 build 的目录投影一致：目录层级对账按投影后的序列进行，
    被投影剔除的文档记录到 ``nav_exempt``。
    """
    result = ProvenanceResult()
    structured_dir = store.structured_dir
    translation_dir = store.translation_dir

    # 期望内容集：与 _render_and_pack 的跳过逻辑镜像（译文优先 → 空壳跳过）
    expected: list[dict[str, Any]] = []
    for e in entries:
        rel = e.get("rel_path")
        if not rel:
            continue
        structured_path = structured_dir / rel
        tgt_path = translation_dir / rel
        md_path = tgt_path if prefer_translation and tgt_path.is_file() else structured_path
        if not structured_path.is_file():
            result.add("warning", "W_STRUCT_MISSING", f"structured 缺失：{e['id']}（{rel}）")
            continue
        if not md_path.is_file():
            continue
        if skip_empty_unit(md_path.read_text(encoding="utf-8"), e.get("title") or ""):
            continue
        expected.append(e)
    result.units_total = len(expected)
    expected_names = [f"{slug_file(e['id'])}.xhtml" for e in expected]

    try:
        zf = zipfile.ZipFile(epub_path)
    except zipfile.BadZipFile:
        result.add("error", "E_NOT_EPUB", f"不是有效的 zip：{epub_path}")
        return result

    with zf:
        spine = _spine_docs(zf)
        nav_depths = _nav_depths(zf)
        declared_depth = _nav_declared_depth(zf)
        opf_has_cover = _opf_has_cover(zf)
        # EPUB 呈现对账（交付审计 S1.2）：按 spine 收集每文档的呈现数据
        opf_dir = _opf_dir(zf)
        zip_names = set(zf.namelist())
        doc_path: dict[str, str] = {}
        for href in spine:
            doc_path[Path(unquote(href)).name] = (Path(opf_dir) / unquote(href)).as_posix()
        doc_text: dict[str, str] = {}
        doc_imgs: dict[str, Counter[str]] = {}
        doc_fn: dict[str, int] = {}
        doc_bilingual: dict[str, bool] = {}
        for name in expected_names:
            zpath = doc_path.get(name)
            if not zpath or zpath not in zip_names:
                continue
            html = zf.read(zpath).decode("utf-8")
            doc_text[name] = re.sub(r"\s+", "", _strip_tags(html))
            doc_imgs[name] = Counter(
                Path(unquote(src)).name
                for src in re.findall(r'<img\b[^>]*?src="([^"]+)"', html, re.IGNORECASE)
            )
            doc_fn[name] = len(re.findall(r"<aside[^>]*epub:type=\"footnote\"", html))
            doc_bilingual[name] = 'class="src"' in html

    spine_docs = [Path(unquote(h)).name for h in spine]
    spine_set = set(spine_docs)
    expected_set = set(expected_names)

    # ── 三边对账：spine vs 期望集（存在性 + 顺序） ────────────────────────
    result.units_missing = [
        e["id"] for e, n in zip(expected, expected_names, strict=False) if n not in spine_set
    ]
    result.units_unexpected = [n for n in spine_docs if n not in expected_set]
    actual_matched = [n for n in spine_docs if n in expected_set]
    result.units_order_ok = actual_matched == [n for n in expected_names if n in spine_set]
    if result.units_missing:
        result.add("error", "E_UNIT_MISSING", "spine 缺少单元：" + "、".join(result.units_missing))
    if result.units_unexpected:
        result.add(
            "error",
            "E_UNIT_ORDER",
            "spine 含未知内容文档：" + "、".join(result.units_unexpected),
        )
    if not result.units_order_ok and not result.units_unexpected:
        result.add("error", "E_UNIT_ORDER", "spine 顺序与单元清单不一致")

    # 封面对账（epub-template-spec §3）：存在封面单元但未声明 cover-image → 提示
    if any(e.get("kind") == "cover" for e in expected) and not opf_has_cover:
        result.add(
            "warning",
            "W_NO_COVER",
            "存在封面单元但 EPUB 未声明 cover-image（封面源图缺失或未识别）",
        )

    # ── 媒体溯源：源文图片 vs 译文图片（数量 + 相对顺序） ─────────────────
    for e in expected:
        rel = e.get("rel_path") or ""
        tgt_path = translation_dir / rel
        if not (prefer_translation and tgt_path.is_file()):
            continue  # 无译文：源↔源恒等
        src_refs = _img_refs((structured_dir / rel).read_text(encoding="utf-8"))
        tgt_refs = _img_refs(tgt_path.read_text(encoding="utf-8"))
        src_count, tgt_count = Counter(src_refs), Counter(tgt_refs)
        for name, cnt in src_count.items():
            if tgt_count.get(name, 0) < cnt:
                result.media_lost.append(f"{e['id']}:{name}")
        tgt_set = set(tgt_refs)
        src_set = set(src_refs)
        if [r for r in src_refs if r in tgt_set] != [r for r in tgt_refs if r in src_set]:
            result.media_order_violations.append(e["id"])
    if result.media_lost:
        result.add("error", "E_MEDIA_LOST", "译文丢失源文图片：" + "、".join(result.media_lost))
    if result.media_order_violations:
        result.add(
            "error",
            "E_MEDIA_ORDER",
            "译文图片相对顺序与源文不一致：" + "、".join(result.media_order_violations),
        )

    # ── EPUB 呈现对账（交付审计 S1.2）：构建用 md ↔ 成品实际包含 ───────────
    # 真实案例：md 引用 72 张图但成品仅 34 张（collect_media 静默丢弃/渲染缺失）。
    probe_total = 0
    probe_covered = 0
    for e, name in zip(expected, expected_names, strict=False):
        text = doc_text.get(name)
        if text is None:
            continue  # 文档缺失已由 units_missing 覆盖
        rel = e.get("rel_path") or ""
        tgt_path = translation_dir / rel
        md_path = (
            tgt_path if (prefer_translation and tgt_path.is_file()) else (structured_dir / rel)
        )
        if not md_path.is_file():
            continue
        md_text = md_path.read_text(encoding="utf-8")
        bilingual = doc_bilingual.get(name, False)
        if not bilingual:
            # 媒体呈现：md 图片引用 ↔ 成品 <img>（双语文档不渲染图，跳过）
            for ref, cnt in Counter(_img_refs(md_text)).items():
                if doc_imgs.get(name, Counter()).get(ref, 0) < cnt:
                    result.epub_media_missing.append(f"{e['id']}:{ref}")
            # 脚注呈现：md 定义数 ↔ 成品 aside 数（双语不渲染脚注，跳过）
            md_defs = len(re.findall(r"(?m)^\s*\[\^[^\]]+\]:", md_text))
            epub_defs = doc_fn.get(name, 0)
            if md_defs != epub_defs:
                result.epub_footnotes_missing.append(
                    f"{e['id']}（md {md_defs} / EPUB {epub_defs}）"
                )
        # 正文段落探针：md 每段（build 同款渲染）应出现在成品文档中
        missing, n = _probe_missing(md_text, text)
        probe_total += n
        probe_covered += n - len(missing)
        for head in missing:
            result.epub_coverage_missing.append(f"{e['id']}:{head}")
    if probe_total:
        result.epub_coverage = probe_covered / probe_total
    if result.epub_media_missing:
        result.add(
            "error",
            "E_MEDIA_EPUB_LOST",
            "成品缺失译文引用的图片：" + "、".join(result.epub_media_missing[:8]),
        )
    if result.epub_footnotes_missing:
        result.add(
            "error",
            "E_FN_EPUB_LOST",
            "成品脚注数与译文不一致：" + "、".join(result.epub_footnotes_missing[:8]),
        )
    if result.epub_coverage_missing:
        result.add(
            "error",
            "E_EPUB_PARA_LOST",
            f"成品缺失译文段落 {len(result.epub_coverage_missing)} 处："
            + "；".join(result.epub_coverage_missing[:5]),
        )

    # ── 逐段覆盖率：structured 每段都能在 align src 侧找到 ────────────────
    total_paras = 0
    covered_paras = 0
    has_align = False
    for e in expected:
        rows = read_align(store.unit_align_path(e["id"]))
        if not rows:
            continue
        has_align = True
        rel = e.get("rel_path") or ""
        # md↔align 一致性（交付审计 S1.1 兜底复核）：防 import 后 md 被单独改动
        # （如丢图片段/脚注）而 align 未同步——防缺陷直达成品
        tgt_path = translation_dir / rel
        if tgt_path.is_file():
            for d in md_align_drift(
                tgt_path.read_text(encoding="utf-8"), rows, title=str(e.get("title") or "") or None
            ):
                result.align_md_drift.append(f"{e['id']}: {d}")
        src_concat = _norm("".join(r.get("src") or "" for r in rows))
        for i, para in enumerate(_paragraphs((structured_dir / rel).read_text(encoding="utf-8"))):
            total_paras += 1
            if _norm(para) in src_concat:
                covered_paras += 1
            else:
                result.coverage_missing.append(f"{e['id']}:{i + 1}")
    if has_align and total_paras:
        result.coverage = covered_paras / total_paras
    if result.align_md_drift:
        result.add(
            "error",
            "E_ALIGN_MD_DRIFT",
            "译文文档与对照表不一致（疑缺内容）：" + "；".join(result.align_md_drift[:3]),
        )

    # ── 目录层级：nav 嵌套深度 vs 源文 level 序列（按 nav_depth 投影后对账）──
    # 投影深度以产物声明为准（构建期写入 nav.xhtml），配置/参数仅兜底旧产物。
    effective_depth = declared_depth if declared_depth is not None else nav_depth
    name2entry = dict(zip(expected_names, expected, strict=False))
    spine_entries = [name2entry[n] for n in spine_docs if n in name2entry]
    nav_candidates = nav_toc_entries(spine_entries, effective_depth)
    nav_names = {f"{slug_file(e['id'])}.xhtml" for e in nav_candidates}
    result.nav_exempt = [
        f"{slug_file(e['id'])}.xhtml"
        for e in spine_entries
        if f"{slug_file(e['id'])}.xhtml" not in nav_names
    ]
    result.toc_depths_expected = toc_depths(nav_candidates)
    result.toc_depths_nav = nav_depths
    if (
        result.toc_depths_expected
        and max(result.toc_depths_expected) > 1
        and (not nav_depths or max(nav_depths) == 1)
    ):
        result.toc_flat = True
        result.add("error", "E_TOC_FLAT", "源文有标题层级，但 nav 目录为扁平单层")
    elif result.toc_depths_expected and nav_depths and result.toc_depths_expected != nav_depths:
        result.toc_depth_mismatch = True
        result.add("warning", "W_TOC_DEPTH", "nav 嵌套深度与源文标题层级序列不一致")

    # ── 插入内容溯源：插图/表格/公式描述文件与原始地址 ────────────────────
    _audit_inserts(result, structured_dir)

    return result
