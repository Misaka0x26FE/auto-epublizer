"""后处理溯源审计（零 token、离线、确定性）。

postprocessing-spec §2/§3 的实现，四类检查全部只出信号不出裁决：

- 三边对账：structured ↔ translation ↔ EPUB spine（E_UNIT_MISSING / E_UNIT_ORDER）
- 媒体溯源：源文图片引用 vs 译文（数量与相对顺序，E_MEDIA_LOST / E_MEDIA_ORDER）
- 逐段覆盖率：structured 正文段落都能在 align 的 src 侧找到 → ``provenance_coverage``
  （无翻译产物时为 None——convert 路径不适用该门）
- 目录层级：EPUB nav 嵌套深度 vs 源文 level 序列（E_TOC_FLAT / W_TOC_DEPTH）
"""

from __future__ import annotations

import math
import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from auto_translator.translation.align import read_align

from ..build import slug_file, toc_depths
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


def _norm(text: str) -> str:
    """归一化：去除全部空白字符（段落↔句子集包含比较用）。"""
    return re.sub(r"\s+", "", text or "")


def _paragraphs(md_text: str) -> list[str]:
    """structured md 的正文段落块（跳过标题行/空块）。"""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", (md_text or "").strip("\n")):
        block = block.strip()
        if block and not block.startswith("#"):
            out.append(block)
    return out


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
    """插入内容溯源审计（raw/inserts/index.jsonl 存在时；pdf-content-spec §9）。

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
) -> ProvenanceResult:
    """对成品 EPUB 执行溯源审计（构建期跳过逻辑与本函数期望集保持一致）。

    ``prefer_translation`` 与 _render_and_pack 语义一致：译文存在时以译文为
    构建/审计基准（媒体对账才有意义），否则源↔源恒等跳过媒体检查。
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

    try:
        zf = zipfile.ZipFile(epub_path)
    except zipfile.BadZipFile:
        result.add("error", "E_NOT_EPUB", f"不是有效的 zip：{epub_path}")
        return result

    with zf:
        spine = _spine_docs(zf)
        nav_depths = _nav_depths(zf)
        opf_has_cover = _opf_has_cover(zf)

    spine_docs = [Path(unquote(h)).name for h in spine]
    expected_names = [f"{slug_file(e['id'])}.xhtml" for e in expected]
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
        src_concat = _norm("".join(r.get("src") or "" for r in rows))
        for i, para in enumerate(_paragraphs((structured_dir / rel).read_text(encoding="utf-8"))):
            total_paras += 1
            if _norm(para) in src_concat:
                covered_paras += 1
            else:
                result.coverage_missing.append(f"{e['id']}:{i + 1}")
    if has_align and total_paras:
        result.coverage = covered_paras / total_paras

    # ── 目录层级：nav 嵌套深度 vs 源文 level 序列 ─────────────────────────
    name2entry = dict(zip(expected_names, expected, strict=False))
    spine_entries = [name2entry[n] for n in spine_docs if n in name2entry]
    result.toc_depths_expected = toc_depths(spine_entries)
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
