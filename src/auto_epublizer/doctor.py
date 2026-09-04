"""环境与能力自检（doctor）：纯只读探测，不改任何状态。

探测三件事，供 agent 在开工前判断能力边界与 ingest 路由：
1. 系统工具链（pandoc / pdftotext / tesseract / ocrmypdf / java + epubcheck jar）；
2. Python 依赖（pymupdf / rapidocr / lxml）；
3. 外部 API 与网络（MinerU key；--ping 时网络可达性）。

唯一 LLM 原则：doctor 不探测任何 LLM——理解/翻译/审校由操作 CLI 的 agent 完成。

``multimodal`` / ``search``（agent 自身是否多模态/是否有搜索工具）CLI 无法探测，
恒为 null，由 agent 自报补填（落盘 preprocessing/capabilities.md）。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from auto_common.config import Config


@dataclass
class Capability:
    """一项能力的探测结果。"""

    name: str
    available: bool
    impact: str  # 缺失时影响什么
    hint: str = ""  # 应对建议
    detail: str = ""  # 版本/错误详情


def _probe_tool(name: str, impact: str, hint: str) -> Capability:
    found = shutil.which(name)
    return Capability(
        name=name,
        available=found is not None,
        impact=impact,
        hint=hint,
        detail=found or "",
    )


def _probe_import(module: str, name: str, impact: str, hint: str) -> Capability:
    spec = importlib.util.find_spec(module)
    return Capability(
        name=name,
        available=spec is not None,
        impact=impact,
        hint=hint,
        detail=module,
    )


def probe_epubcheck(config: Config) -> Capability:
    jar = Path(config.qc.epubcheck.jar).expanduser()
    java = shutil.which("java")
    if not jar.is_file():
        return Capability(
            name="epubcheck",
            available=False,
            impact="G4 无法跑 epubcheck，released 恒 False",
            hint="下载 https://github.com/w3c/epubcheck/releases 放到 "
            f"{config.qc.epubcheck.jar}（需 java）",
        )
    return Capability(
        name="epubcheck",
        available=java is not None,
        impact="" if java else "jar 已装但缺 java，仍无法运行",
        hint="" if java else "安装 java（apt-get install default-jre）",
        detail=str(jar),
    )


def probe_mineru() -> Capability:
    """外部解析 API MinerU：探测 MINERU_API_KEY 环境变量（本地只读，无网络）。"""
    key = os.environ.get("MINERU_API_KEY", "")
    return Capability(
        name="mineru",
        available=bool(key),
        impact="无 MinerU API key：复杂版面 PDF 无法走外部解析 API（MinerU Open Source License）",
        hint="export MINERU_API_KEY=..." if not key else "",
        detail="env MINERU_API_KEY" if key else "",
    )


def probe_network(timeout: float = 5.0) -> Capability:
    """外部网络可达性（--ping 才执行；多 host 任一可达即判有网络）。"""
    import httpx

    for url in ("https://www.baidu.com", "https://github.com"):
        try:
            httpx.get(url, timeout=timeout)
            return Capability(name="network", available=True, impact="", detail=url)
        except Exception:  # noqa: BLE001
            continue
    return Capability(
        name="network",
        available=False,
        impact="外部网络不可达：无网络检索/外部 API 兜底",
        hint="如需背景知识补齐，请用户提供参考信息（references/user/）",
    )


def collect_capabilities(config: Config, *, ping: bool = False) -> list[Capability]:
    """收集全部能力探测结果（纯只读）。"""
    caps: list[Capability] = [
        _probe_tool(
            "pandoc",
            "EPUB/DOCX/HTML 输入无法直接处理",
            "apt-get install pandoc，或先把文件转为 PDF/TXT/MD",
        ),
        _probe_tool(
            "pdftotext",
            "PDF 文字层备用提取缺失（主路径为 pymupdf）",
            "apt-get install poppler-utils",
        ),
        _probe_tool(
            "tesseract",
            "扫描 PDF 无离线 OCR 备选（主路径为 rapidocr）",
            "apt-get install tesseract-ocr",
        ),
        _probe_tool(
            "ocrmypdf",
            "扫描 PDF 无传统 OCR 文字层重建（tesseract 之上的首选）",
            "pip install ocrmypdf（依赖 tesseract）",
        ),
        _probe_import("fitz", "pymupdf", "PDF 文字层按页切片不可用", "uv sync（自带依赖）"),
        _probe_import(
            "rapidocr_onnxruntime",
            "rapidocr",
            "扫描 PDF 无法离线 OCR",
            "uv sync --extra ocr",
        ),
        _probe_import("lxml", "lxml", "HTML 预处理能力受限", "uv sync（自带依赖）"),
        probe_epubcheck(config),
        probe_mineru(),
    ]
    if ping:
        caps.append(probe_network())
    return caps


def capabilities_summary(caps: list[Capability]) -> dict[str, Any]:
    """能力报告（JSON 可序列化）；multimodal/search 留 null 由 agent 自报。"""
    return {
        "capabilities": {
            c.name: {
                "available": c.available,
                "impact": c.impact,
                "hint": c.hint,
                "detail": c.detail,
            }
            for c in caps
        },
        "multimodal": None,  # agent 自报：能否看图（决定扫描 PDF 视觉兜底）
        "search": None,  # agent 自报：是否有网络搜索工具（决定背景知识补齐路由）
    }
