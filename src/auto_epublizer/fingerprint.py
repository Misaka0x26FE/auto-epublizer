# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""成品软件来源：实际工具快照、可见声明和离线机器指纹，不作遥测或书稿授权。"""

from __future__ import annotations

import contextlib
import json
import platform
import re
import subprocess
import xml.etree.ElementTree as ET
from html import escape
from importlib import metadata
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from auto_common.workspace import Publication
from auto_common.workspace.models import validate_generation_tools

from . import __version__

PROJECT_NAME = "auto-epublizer"
PROJECT_URL = "https://github.com/Misaka0x26FE/auto-epublizer"
PROJECT_LICENSE = "AGPL-3.0-only"
VOCAB_URL = PROJECT_URL + "/vocab#"
_COMMENT_PREFIX = "auto-epublizer-build "
_COMMENTS = re.compile(r"<!--(.*?)-->", re.DOTALL)
# 名称、项目地址、许可、Python 分发名；只在真实调用路径选择，不枚举安装环境。
_TOOLS = {
    "python": ("Python", "https://www.python.org/", "PSF-2.0", None),
    "pydantic": ("Pydantic", "https://github.com/pydantic/pydantic", "MIT", "pydantic"),
    "pymupdf": ("PyMuPDF", "https://github.com/pymupdf/PyMuPDF", "AGPL-3.0", "pymupdf"),
    "pandoc": ("Pandoc", "https://pandoc.org/", "GPL-2.0-or-later", None),
    "calibre": ("calibre", "https://calibre-ebook.com/", "GPL-3.0-only", None),
    "rapidocr": (
        "RapidOCR",
        "https://github.com/RapidAI/RapidOCR",
        "Apache-2.0",
        "rapidocr-onnxruntime",
    ),
    "httpx": ("HTTPX", "https://github.com/encode/httpx", "BSD-3-Clause", "httpx"),
    "mineru": ("MinerU API", "https://mineru.net/", None, None),
}
# 制作页可见的出版/版权信息顺序与中英标签（zh 权威、en 派生）。
_PUBLICATION_FIELDS = (
    ("title", "书名", "Title"),
    ("creator", "作者", "Creator"),
    ("translator", "译者", "Translator"),
    ("publisher", "出版社", "Publisher"),
    ("date", "出版日期", "Date"),
    ("rights", "版权/许可", "Rights"),
)


def used_tool(key: str) -> dict[str, str | None]:
    """为已调用的工具取得当时版本；不可得保持 None，不伪造版本或服务许可。"""
    name, url, license_id, distribution = _TOOLS[key]
    version: str | None = None
    if key == "python":
        version = platform.python_version()
    elif distribution:
        with contextlib.suppress(metadata.PackageNotFoundError):
            version = metadata.version(distribution)
    elif key in ("pandoc", "calibre"):
        command = "pandoc" if key == "pandoc" else "ebook-convert"
        try:
            proc = subprocess.run(
                [command, "--version"], capture_output=True, text=True, timeout=5, check=False
            )
            if proc.returncode == 0:
                first = (proc.stdout or proc.stderr).splitlines()
                match = re.search(r"\b\d+(?:\.\d+)+(?:[\w.+-]*)", first[0]) if first else None
                if match:
                    version = match.group(0)
        except (OSError, subprocess.SubprocessError):
            pass
    return {
        "name": name,
        "version": version,
        "url": url,
        "license": license_id,
        "kind": "service" if key == "mineru" else "software",
    }


def _revision() -> tuple[str | None, bool | None]:
    """只识别当前包的源码仓库；安装包或无 git 时明确未知，不读取用户工作区 git。"""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists() or not (root / "pyproject.toml").is_file():
        return None, None
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if commit.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", commit.stdout.strip()):
            return None, None
        state = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--",
                "src",
                "pyproject.toml",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return commit.stdout.strip(), bool(state.stdout) if state.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None, None


def _publication_fields(pub: Publication) -> dict[str, str]:
    """制作页可见的出版/版权信息：只收非空字段，空值不渲染也不猜测。"""
    out: dict[str, str] = {}
    for key, *_ in _PUBLICATION_FIELDS:
        value = getattr(pub.meta, key, None)
        if isinstance(value, str) and value.strip():
            out[key] = value
    return out


def build_fingerprint(pub: Publication) -> dict[str, Any]:
    """构建时身份与已冻结的 ingest 工具分开；绝不拿 init producer 充当构建版本。"""
    revision, dirty = _revision()
    return {
        "schema_version": 1,
        "project": {
            "name": PROJECT_NAME,
            "url": PROJECT_URL,
            "license": PROJECT_LICENSE,
            "version": __version__,
            "revision": revision,
            "dirty": dirty,
        },
        "runtime": [used_tool("python"), used_tool("pydantic")],
        "processing_tools": pub.meta.processing_tools,
        "publication": _publication_fields(pub),
        "generation_tools": pub.meta.generation_tools,
        "generated_page": None,
    }


def fingerprint_json(data: dict[str, Any]) -> str:
    text = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return text.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")


def _valid(data: Any) -> bool:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return False
    project = data.get("project")
    try:
        validate_generation_tools(data.get("generation_tools"))
    except ValueError:
        return False
    return (
        isinstance(project, dict)
        and project.get("name") == PROJECT_NAME
        and project.get("url") == PROJECT_URL
        and project.get("license") == PROJECT_LICENSE
        and isinstance(project.get("version"), str)
        and bool(project["version"].strip())
        and isinstance(data.get("runtime"), list)
        and (data.get("processing_tools") is None or isinstance(data["processing_tools"], list))
        and isinstance(data.get("publication", {}), dict)
        and all(isinstance(v, str) for v in data.get("publication", {}).values())
        and (data.get("generation_tools") is None or isinstance(data["generation_tools"], list))
        and (data.get("generated_page") is None or isinstance(data["generated_page"], str))
    )


def _comment_data(body: str) -> dict[str, Any] | None:
    text = body.strip()
    if not text.startswith(_COMMENT_PREFIX):
        return None
    try:
        data = json.loads(text[len(_COMMENT_PREFIX) :])
    except ValueError:
        return None
    return data if _valid(data) else None


def strip_fingerprint_comments(text: str) -> str:
    """仅豁免本项目有效结构指纹；任意普通/伪造前缀/坏 JSON 注释仍留给残留门。"""
    return _COMMENTS.sub(
        lambda m: "" if _comment_data(m.group(1)) is not None else m.group(0), text
    )


def _link(url: str, text: str) -> str:
    if not url.startswith(("https://", "http://")):
        return escape(text)
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def _next_heading(heading: str) -> str:
    """子块标题按父标题降一级（h1→h2），无法识别时退回 h2。"""
    match = re.fullmatch(r"h([1-6])", heading)
    return f"h{min(int(match.group(1)) + 1, 6)}" if match else "h2"


def _publication_block(data: dict[str, Any], lang: str, *, heading: str) -> str:
    """出版/版权信息块；无非空字段时整块省略，不输出空标签。"""
    zh = lang.lower().startswith("zh")
    fields = data.get("publication") or {}
    separator = "：" if zh else ": "
    rows = [
        f"<li>{escape(label_zh if zh else label_en)}{separator}{escape(str(fields[key]))}</li>"
        for key, label_zh, label_en in _PUBLICATION_FIELDS
        if isinstance(fields.get(key), str) and fields[key].strip()
    ]
    if not rows:
        return ""
    title = "版权与出版信息" if zh else "Publication and rights information"
    sub = _next_heading(heading)
    return f"<{sub}>{title}</{sub}><ul>{''.join(rows)}</ul>"


def _generation_items(data: dict[str, Any], lang: str) -> str:
    """生成模型（LLM）署名条目：name version — task；未知值如实标注，不伪造。"""
    zh = lang.lower().startswith("zh")
    if data.get("generation_tools") == []:
        return (
            "<li>明确未使用生成模型（agent 自报）。</li>"
            if zh
            else "<li>No generation model was used (agent-reported).</li>"
        )
    items = []
    for tool in data.get("generation_tools") or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or ("未署名工具" if zh else "unnamed tool"))
        version = tool.get("version") or ("版本未记录" if zh else "version unrecorded")
        task = tool.get("task") or ("任务未记录" if zh else "task unrecorded")
        items.append(f"<li>{escape(name)} {escape(str(version))} — {escape(str(task))}</li>")
    if not items:
        return ""
    label = "生成模型（LLM）" if zh else "Generation models (LLM)"
    return f"<li>{label}<ul>{''.join(items)}</ul></li>"


def software_section(data: dict[str, Any], lang: str, *, heading: str = "h2") -> str:
    """独立软件声明，不改动作者、译者和作品权利。"""
    zh = lang.lower().startswith("zh")
    title = "制作工具与开源软件" if zh else "Production software and open-source tools"
    disclaimer = (
        "以下许可仅说明软件，不授予或改变本书正文、译文及插图的权利。"
        if zh
        else "These licenses describe software only; they do not grant or change rights to this book, its translation or illustrations."
    )
    tools = [*data["runtime"], *(data["processing_tools"] or [])]
    lines = []
    for tool in tools:
        version = tool.get("version") or ("版本未记录" if zh else "version unrecorded")
        license_id = tool.get("license") or (
            "服务；许可未声明" if zh else "service; license not declared"
        )
        name = _link(str(tool.get("url") or ""), str(tool["name"]))
        lines.append(f"<li>{name} — {escape(version)} ({escape(license_id)})</li>")
    history = ""
    if data["processing_tools"] is None:
        history = (
            "<p>上游处理工具：旧工作区未记录，无法由当前安装环境追溯。</p>"
            if zh
            else "<p>Upstream processing tools were not recorded; the current installation cannot establish their history.</p>"
        )
    elif not data["processing_tools"]:
        history = (
            "<p>上游处理未使用额外外部解析工具。</p>"
            if zh
            else "<p>No additional external parsing tool was used upstream.</p>"
        )
    project = data["project"]
    revision = project.get("revision") or ("未记录" if zh else "unrecorded")
    dirty = " (modified source)" if project.get("dirty") else ""
    return (
        '<section class="software-provenance">'
        f"<{heading}>{title}</{heading}>"
        f"<p>{_link(PROJECT_URL, PROJECT_NAME)} {escape(project['version'])} — {PROJECT_LICENSE}</p>"
        f"<p>Revision: {escape(revision)}{dirty}</p>"
        f"<p>{disclaimer}</p>{history}"
        f"{_publication_block(data, lang, heading=heading)}"
        f"<ul>{_generation_items(data, lang)}{''.join(lines)}</ul></section>"
    )


def stamp_document(text: str, data: dict[str, Any], lang: str, *, visible: bool = False) -> str:
    """在 head 写可解析 JSON 注释，可选在版权正文尾部加独立软件声明。"""
    text = strip_fingerprint_comments(text)
    # XML 注释禁止 --；JSON Unicode 转义保持解码后内容完全相同。
    payload = fingerprint_json(data).replace("--", r"-\u002d")
    comment = f"<!-- {_COMMENT_PREFIX}{payload} -->\n"
    text = text.replace("</head>", comment + "</head>", 1)
    if visible:
        text = text.replace("</body>", software_section(data, lang) + "\n</body>", 1)
    return text


def software_page(data: dict[str, Any], lang: str) -> str:
    title = "制作信息" if lang.lower().startswith("zh") else "Production information"
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{escape(lang, quote=True)}">'
        '<head><meta charset="utf-8"/><meta name="auto-epublizer:generated" content="build-info"/>'
        f'<link rel="stylesheet" href="style.css"/><title>{title}</title></head>'
        f"<body>{software_section(data, lang, heading='h1')}</body></html>"
    )
    return stamp_document(text, data, lang)


def generated_pages(zf: ZipFile) -> set[str]:
    """只识别 OPF 声明且页内指纹一致的制作页；不按文件名盲目豁免未知文档。"""
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = next(n for n in container.iter() if n.tag.endswith("}rootfile"))
        opf_path = rootfile.attrib["full-path"]
        opf = ET.fromstring(zf.read(opf_path))
        value = next(n.text for n in opf.iter() if n.attrib.get("property") == "aep:build")
        data = json.loads(value or "")
        if not _valid(data):
            return set()
        name = data.get("generated_page")
        if not name or Path(name).name != name:
            return set()
        text = zf.read((Path(opf_path).parent / name).as_posix()).decode("utf-8")
        page = ET.fromstring(text)
        marked = any(
            n.attrib.get("name") == "auto-epublizer:generated"
            and n.attrib.get("content") == "build-info"
            for n in page.iter()
        )
        matching = any(_comment_data(m.group(1)) == data for m in _COMMENTS.finditer(text))
        return {name} if marked and matching else set()
    except (KeyError, ValueError, StopIteration, ET.ParseError):
        return set()
