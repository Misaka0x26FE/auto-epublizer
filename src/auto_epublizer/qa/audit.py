"""EPUB 解包逐项审计：结构性检查（零 token、离线）。"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_XHTML = "application/xhtml+xml"
_HTTPS = re.compile(r"^(https?|javascript|data):", re.IGNORECASE)


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

    return result
