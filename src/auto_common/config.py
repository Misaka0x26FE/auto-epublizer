"""pydantic 配置模型：对齐 docs/configuration.md 的目标 schema。

唯一 LLM 原则：CLI 只做确定性、零 token 计算，配置中没有任何 LLM provider 段；
一切语义工作由操作 CLI 的 agent 用自身能力完成。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

# 统一术语库/知识库的**公共**远端（跨设备同步 + 他人只读订阅）。
# 固化在软件里，使 knowledge init 在任何设备上都无需手填 --remote；
# 自建库/fork 用 --remote、环境变量 AUTO_EPUBLIZER_REMOTE 或配置 paths.knowledge_remote 覆盖。
DEFAULT_KNOWLEDGE_REMOTE = "https://github.com/Misaka0x26FE/auto-epublizer-knowledge.git"


class LanguageConfig(BaseModel):
    source: str = "auto"
    target: str = "zh-CN"
    genre: str = "auto"


class PipelineConfig(BaseModel):
    bilingual: bool = False


class EpubcheckConfig(BaseModel):
    # pydantic v2 默认值不走 field_validator，必须显式 validate_default 展开 `~`
    jar: str = Field(default="~/.cache/epubcheck.jar", validate_default=True)
    strict: bool = True

    @field_validator("jar")
    @classmethod
    def expand_home(cls, value: str) -> str:
        return str(Path(value).expanduser())


class QCConfig(BaseModel):
    length_ratio: dict[str, float] = Field(
        default_factory=lambda: {"too_short": 0.30, "too_long": 3.0}
    )
    epubcheck: EpubcheckConfig = Field(default_factory=EpubcheckConfig)


class PDFConfig(BaseModel):
    backend: str = "auto"  # auto | pymupdf | mineru（auto=扫描件且 key 存在时优先 MinerU）
    ocr: str = "auto"
    page_dpi: int = 300
    mineru_effort: str = "medium"  # 未接线（MinerU v4 API 无此参数）；保留兼容旧配置
    mineru_model: str = "pipeline"  # pipeline（默认，确定性）| vlm（高精度，内部为 VLM）
    mineru_language: str = "ch"  # MinerU OCR 语言（PaddleOCR 语言码：ch/en/ja/…）
    mineru_batch_pages: int = 200  # >此页数自动分批（MinerU 单文件 ≤200 页限制；≤0 关闭）
    # PDF 文字层 RTL（从右向左）处理：auto=按文字层自动判定；on/off=强制。
    # RTL 书逐行做方向控制符剥离 + NFKC 归一化 + 逻辑词序还原（见 ingest/rtl.py）。
    rtl: str = "auto"


class GlossaryConfig(BaseModel):
    storage: str = "csv"
    scope: str = "chapter"


class PathsConfig(BaseModel):
    workspaces_dir: str = "."
    # 统一术语库/知识库持久化目录；空串=默认 ~/Documents/auto-epublizer
    # 覆盖优先级：--dir > 环境变量 AUTO_EPUBLIZER_HOME > 本项 > 默认
    knowledge_dir: str = ""
    # 统一库 git 远端（跨设备同步 + 公共知识库）；已固化项目公共仓库地址，
    # knowledge init 无需 --remote 即可直接配好远端（fork/自建库用 --remote 或本项覆盖）
    # 覆盖优先级：--remote > 环境变量 AUTO_EPUBLIZER_REMOTE > 本项 > DEFAULT_KNOWLEDGE_REMOTE
    knowledge_remote: str = DEFAULT_KNOWLEDGE_REMOTE


class OutputConfig(BaseModel):
    mono: bool = True
    bilingual: bool = False
    about_page: bool = True
    theme: str = "standard"  # standard | compact | spacious（epub-template-spec §5）
    nav_depth: int = Field(3, ge=1, le=6)  # 目录最大嵌套深度（epub-template-spec §3 投影）


class Config(BaseModel):
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    qc: QCConfig = Field(default_factory=QCConfig)
    pdf: PDFConfig = Field(default_factory=PDFConfig)
    glossary: GlossaryConfig = Field(default_factory=GlossaryConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def load_config(path: str | Path | None = None) -> Config:
    data: dict[str, Any] = {}
    if path is not None:
        p = Path(path)
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            data.update(raw)
    return Config.model_validate(data)
