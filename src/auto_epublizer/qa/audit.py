"""EPUB 解包逐项审计：结构性检查（零 token、离线）。"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_XHTML = "application/xhtml+xml"
_HTTPS = re.compile(r"^(https?|javascript|data):", re.IGNORECASE)

# 体积阈值（postprocessing-spec P2 体积审计；可按需调整）
_MAX_EPUB_BYTES = 50 * 1024 * 1024
_MAX_IMG_BYTES = 2 * 1024 * 1024
_MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".avif")


@dataclass
class AuditFinding:
    level: str  # error | warning
    code: str
    message: str


@dataclass
class AuditResult:
    ok: bool
    findings: list[AuditFinding] = field(default_factory=list)

    def add(self, level: str, code: str, message: str) -> None:
        self.findings.append(AuditFinding(level=level, code=code, message=message))
        if level == "error":
            self.ok = False


def _image_size(data: bytes, ext: str) -> tuple[int, int] | None:
    """解析 png/jpg/gif/bmp 的像素尺寸（其余格式或解析失败返回 None）。"""
    try:
        if ext == ".png" and len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if ext == ".gif" and len(data) >= 10 and data[:3] == b"GIF":
            return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
        if ext == ".bmp" and len(data) >= 26 and data[:2] == b"BM":
            return (
                abs(int.from_bytes(data[18:22], "little")),
                abs(int.from_bytes(data[22:26], "little")),
            )
        if ext in (".jpg", ".jpeg") and data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3):  # SOF：含宽高
                    h = int.from_bytes(data[i + 5 : i + 7], "big")
                    w = int.from_bytes(data[i + 7 : i + 9], "big")
                    return w, h
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:  # 无长度段
                    i += 2
                    continue
                seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
                if seg_len < 2:
                    return None
                i += 2 + seg_len
        return None
    except IndexError:
        return None


def audit_epub(path: str | Path) -> AuditResult:
    """解包 EPUB 并逐项审计结构。"""
    result = AuditResult(ok=True)
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        result.add("error", "E_NOT_EPUB", f"不是有效的 zip：{e}")
        return result

    with zf:
        names = zf.namelist()

        # 1. mimetype 首位未压缩、内容正确
        if not names or names[0] != "mimetype":
            result.add("error", "E_MIMETYPE_FIRST", "mimetype 必须是 zip 首个条目")
        else:
            info = zf.getinfo("mimetype")
            if info.compress_type != zipfile.ZIP_STORED:
                result.add("error", "E_MIMETYPE_STORED", "mimetype 不得压缩")
            if zf.read("mimetype").decode("utf-8") != "application/epub+zip":
                result.add("error", "E_MIMETYPE_CONTENT", "mimetype 内容错误")

        # 2. container.xml 指向 OPF
        if "META-INF/container.xml" not in names:
            result.add("error", "E_NO_CONTAINER", "缺少 META-INF/container.xml")
            return result
        container = zf.read("META-INF/container.xml").decode("utf-8")
        m = re.search(r'full-path="([^"]+)"', container)
        if not m:
            result.add("error", "E_CONTAINER_OPF", "container.xml 未声明 OPF")
            return result
        opf_path = m.group(1)

        # 3. OPF 解析 manifest/spine
        if opf_path not in names:
            result.add("error", "E_OPF_MISSING", f"OPF 缺失：{opf_path}")
            return result
        opf = zf.read(opf_path).decode("utf-8")
        manifest_hrefs = set(re.findall(r'<item[^>]+href="([^"]+)"', opf))
        spine_idrefs = set(re.findall(r'<itemref[^>]+idref="([^"]+)"', opf))
        manifest_ids = set(re.findall(r'<item[^>]+id="([^"]+)"', opf))

        for idref in spine_idrefs:
            if idref not in manifest_ids:
                result.add("error", "E_SPINE_REF", f"spine idref 未在 manifest：{idref}")

        opf_dir = Path(opf_path).parent
        for href in manifest_hrefs:
            full = (opf_dir / href).as_posix()
            if full not in names:
                result.add("error", "E_MANIFEST_HREF", f"manifest href 无法解析：{href}")

        # 4. nav / NCX / landmarks 链接可解析（引用不存在的文件即悬空）
        nav_entries = [n for n in names if n.endswith("nav.xhtml")]
        for nav in nav_entries:
            content = zf.read(nav).decode("utf-8")
            for href in re.findall(r'href="([^"]+\.xhtml)"', content):
                full = (Path(nav).parent / href).as_posix()
                if full not in names:
                    result.add("error", "E_NAV_HREF", f"nav 链接无法解析：{href}")

        for ncx in (n for n in names if n.endswith(".ncx")):
            content = zf.read(ncx).decode("utf-8")
            for src in re.findall(r'<content src="([^"]+)"', content):
                full = (Path(ncx).parent / src).as_posix()
                if full not in names:
                    result.add("error", "E_NCX_HREF", f"NCX content src 无法解析：{src}")

        for lm in (n for n in names if n.endswith("landmarks.xhtml")):
            content = zf.read(lm).decode("utf-8")
            for href in re.findall(r'href="([^"]+\.xhtml)"', content):
                full = (Path(lm).parent / href).as_posix()
                if full not in names:
                    result.add("error", "E_LANDMARKS_HREF", f"landmarks 链接无法解析：{href}")

        # 4b. 内容文档 <img src> 引用必须存在于包内（媒体悬空检测）
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            content = zf.read(name).decode("utf-8")
            for src in re.findall(r'<img\b[^>]*?src="([^"]+)"', content):
                if _HTTPS.match(src):
                    continue
                full = (Path(name).parent / src).as_posix()
                if full not in names:
                    result.add("error", "E_IMG_SRC", f"img src 无法解析：{name} -> {src}")

        # 5. URL 安全：无 javascript:/data: 注入
        for name in names:
            if not name.endswith(".xhtml") and not name.endswith(".opf"):
                continue
            content = zf.read(name).decode("utf-8")
            if re.search(r'href="\s*(javascript|data):', content, re.IGNORECASE):
                result.add("error", "E_UNSAFE_URL", f"发现危险 URL 注入：{name}")

        # 5b. 主题层校验（epub-template-spec §5）：禁具体字体名/颜色/字号，
        # serif/sans-serif 等泛化族名允许（阅读器映射到自己的字体）。
        if "OEBPS/style.css" in names:
            css = re.sub(
                r"/\*.*?\*/", "", zf.read("OEBPS/style.css").decode("utf-8"), flags=re.DOTALL
            )
            if re.search(r"font-family\s*:[^;}]*[\"']", css):
                result.add(
                    "error",
                    "E_THEME_FONT",
                    "style.css 含具体字体名（只允许 serif/sans-serif 泛化族名）",
                )
            if re.search(r"\bfont-size\s*:", css):
                result.add("error", "E_THEME_FONT", "style.css 设置了字号（应由阅读器决定）")
            if re.search(r"(?<![-\w])color\s*:", css):
                result.add("error", "E_THEME_COLOR", "style.css 设置了颜色（应由阅读器处理）")

        # 5c. 媒体审计（postprocessing-spec P1）：alt 空值/缺失、格式兼容、超大/超宽超高
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            content = zf.read(name).decode("utf-8")
            for tag in re.findall(r"<img\b[^>]*?/?>", content):
                malt = re.search(r'\balt="([^"]*)"', tag)
                if malt is None or not malt.group(1).strip():
                    result.add("warning", "W_IMG_NO_ALT", f"img alt 为空或缺失：{name}")
                msrc = re.search(r'src="([^"]+)"', tag)
                if not msrc:
                    continue
                src = msrc.group(1)
                if _HTTPS.match(src):
                    continue
                full = (Path(name).parent / src).as_posix()
                if full not in names:
                    continue  # 悬空已由 E_IMG_SRC 覆盖
                ext = Path(src).suffix.lower()
                if ext in (".avif", ".webp"):
                    result.add("warning", "W_IMG_FORMAT", f"图片格式阅读器兼容性差（{ext}）：{src}")
                size = _image_size(zf.read(full), ext)
                if size:
                    w, h = size
                    if w > 4000:
                        result.add("warning", "W_IMG_LARGE", f"图片宽度过大（{w}px）：{src}")
                    ratio = max(w, h) / max(min(w, h), 1)
                    if ratio > 5:
                        result.add("warning", "W_IMG_RATIO", f"超宽/超高图（{w}x{h}）：{src}")

        # 6. 内容文档 lang 正确、恰好一个 h1
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            if "xml:lang=" not in content and "lang=" not in content:
                result.add("warning", "W_NO_LANG", f"内容文档缺少 lang：{name}")
            h1s = re.findall(r"<h1\b", content, re.IGNORECASE)
            if len(h1s) != 1:
                result.add("warning", "W_H1_COUNT", f"内容文档 h1 数量不为 1：{name}")

        # 7. 封面 meta 一致性（epub-template-spec §3）：properties 与 <meta name="cover"> 互证
        has_cover_prop = 'properties="cover-image"' in opf
        cover_meta = re.search(r'<meta name="cover" content="([^"]+)"', opf)
        if has_cover_prop and not cover_meta:
            result.add(
                "error", "E_COVER_META", 'manifest 声明 cover-image 但缺 <meta name="cover">'
            )
        elif cover_meta and not has_cover_prop:
            result.add(
                "error",
                "E_COVER_META",
                '<meta name="cover"> 指向的条目未声明 properties="cover-image"',
            )
        elif cover_meta and cover_meta.group(1) not in manifest_ids:
            result.add("error", "E_COVER_META", f"cover meta 指向未知条目：{cover_meta.group(1)}")

        # 8. 标题跳级（postprocessing-spec P2）：h1→h3 等跳级
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            levels = [int(m) for m in re.findall(r"<h([1-6])\b", content, re.IGNORECASE)]
            for prev, cur in zip(levels, levels[1:]):
                if cur > prev + 1:
                    result.add("error", "E_HEADING_SKIP", f"标题跳级 h{prev}→h{cur}：{name}")
                    break

        # 9. 残留检查（postprocessing-spec P2）：HTML 注释=error；markdown/pandoc 标记=warning
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            if "<!--" in content:
                result.add("error", "E_RESIDUE", f"HTML 注释残留：{name}")
            for marker in ("![", "**", ":::", "{.", "[^"):
                if marker in content:
                    result.add("warning", "W_RESIDUE", f"markdown 标记残留（{marker}）：{name}")
                    break

        # 10. 元数据完备（postprocessing-spec P2）：次级 DC 项缺失提示（供 agent 补全）
        missing_meta = [
            tag
            for tag, needle in (
                ("dc:creator", "<dc:creator>"),
                ("dc:date", "<dc:date>"),
                ("dc:publisher", "<dc:publisher>"),
                ("dc:rights", "<dc:rights>"),
            )
            if needle not in opf
        ]
        if missing_meta:
            result.add("warning", "W_META_INCOMPLETE", "DC 元数据缺失：" + "、".join(missing_meta))

        # 11. 内部锚点与脚注回链（postprocessing-spec P2）
        for name in names:
            if not name.endswith(".xhtml"):
                continue
            content = zf.read(name).decode("utf-8")
            ids = set(re.findall(r'\bid="([^"]+)"', content))
            for href in re.findall(r'href="#([^"]+)"', content):
                if href not in ids:
                    result.add("error", "E_ANCHOR", f"内部锚点无法解析（#{href}）：{name}")
            for m in re.finditer(
                r'<aside[^>]*epub:type="footnote"[^>]*id="([^"]+)"[^>]*>(.*?)</aside>',
                content,
                re.DOTALL,
            ):
                fn_id, body = m.group(1), m.group(2)
                back = re.findall(r'href="#([^"]+)"', body)
                if not back or back[0] not in ids:
                    result.add(
                        "error", "E_FN_BACKLINK", f"脚注 {fn_id} 缺回链或回链不可解析：{name}"
                    )

        # 12. 双语成对（postprocessing-spec P2）：class=src/tgt 段落数一致
        for name in names:
            if not name.endswith(".xhtml") or name.endswith(("nav.xhtml", "landmarks.xhtml")):
                continue
            content = zf.read(name).decode("utf-8")
            n_src = len(re.findall(r'<p class="src"', content))
            n_tgt = len(re.findall(r'<p class="tgt"', content))
            if (n_src or n_tgt) and n_src != n_tgt:
                result.add(
                    "error", "E_BI_PAIRS", f"双语 src/tgt 段落数不一致（{n_src}/{n_tgt}）：{name}"
                )

        # 13. 体积审计（postprocessing-spec P2）：告警不阻断
        total = sum(i.file_size for i in zf.infolist())
        if total > _MAX_EPUB_BYTES:
            result.add("warning", "W_EPUB_SIZE", f"EPUB 体积过大：{total // (1024 * 1024)}MB")
        for item in zf.infolist():
            if (
                Path(item.filename).suffix.lower() in _MEDIA_EXTS
                and item.file_size > _MAX_IMG_BYTES
            ):
                result.add(
                    "warning",
                    "W_IMG_UNCOMPRESSED",
                    f"图片过大（{item.file_size // 1024}KB，建议压缩）：{item.filename}",
                )

    return result
