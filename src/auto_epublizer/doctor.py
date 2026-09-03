"""环境与能力自检（doctor）：纯只读探测，不改任何状态。

探测三件事，供 agent 在开工前判断能力边界与 ingest 路由：
1. 系统工具链（pandoc / pdftotext / tesseract / java + epubcheck jar）；
2. Python 依赖（pymupdf / rapidocr / lxml）；
3. LLM 可用性（API Key、视觉模型配置；--ping 时端点连通性）。

``multimodal``（agent 自身是否多模态）CLI 无法探测，恒为 null，由 agent 自报补填。
"""

from __future__ import annotations

import importlib.util
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


def probe_llm(config: Config, *, ping: bool = False) -> list[Capability]:
    """LLM 相关能力：Key / 视觉模型 / （可选）端点连通性。"""
    caps: list[Capability] = []
    key = config.llm.api_key()
    caps.append(
        Capability(
            name="llm_key",
            available=bool(key),
            impact="无 Key 时 analyze/translate/review 走 agent 手写路径（LLM 降级）",
            hint=f"export {config.llm.api_key_env}=..." if not key else "",
        )
    )
    caps.append(
        Capability(
            name="llm_vision_model",
            available=bool(config.llm.vision_model),
            impact="未配置视觉模型时，扫描 PDF 只能离线 OCR，无视觉 LLM 兜底",
            hint="config.yaml: llm.vision_model: <多模态模型 ID>"
            if not config.llm.vision_model
            else "",
            detail=config.llm.vision_model or "",
        )
    )
    if ping:
        caps.append(_ping_endpoint(config))
    return caps


def _ping_endpoint(config: Config, timeout: float = 10.0) -> Capability:
    """向 chat/completions 发最小请求验证连通性（有网络超时风险，--ping 才执行）。"""
    import httpx

    try:
        tier_cfg = next(iter(config.llm.tiers.values()))
        model = tier_cfg.model if tier_cfg else ""
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        headers = {"Content-Type": "application/json"}
        key = config.llm.api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        resp = httpx.post(
            f"{config.llm.base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        ok = resp.status_code == 200
        return Capability(
            name="llm_endpoint",
            available=ok,
            impact="" if ok else f"端点不可用（HTTP {resp.status_code}）",
            detail=resp.text[:120] if not ok else f"{config.llm.base_url}",
        )
    except Exception as e:  # noqa: BLE001
        return Capability(
            name="llm_endpoint",
            available=False,
            impact="端点连通性探测失败",
            detail=str(e)[:160],
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
        _probe_import("fitz", "pymupdf", "PDF 文字层按页切片不可用", "uv sync（自带依赖）"),
        _probe_import(
            "rapidocr_onnxruntime",
            "rapidocr",
            "扫描 PDF 无法离线 OCR",
            "uv sync --extra ocr",
        ),
        _probe_import("lxml", "lxml", "HTML 预处理能力受限", "uv sync（自带依赖）"),
        probe_epubcheck(config),
        *probe_llm(config, ping=ping),
    ]
    return caps


def capabilities_summary(caps: list[Capability]) -> dict[str, Any]:
    """能力报告（JSON 可序列化）；multimodal 留 null 由 agent 自报。"""
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
    }
