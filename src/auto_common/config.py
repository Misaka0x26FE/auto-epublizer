"""pydantic 配置模型：对齐 docs/configuration.md 的目标 schema。

唯一 LLM 原则：CLI 只做确定性、零 token 计算，配置中没有任何 LLM provider 段；
一切语义工作由操作 CLI 的 agent 用自身能力完成。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


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
    backend: str = "auto"
    ocr: str = "auto"
    page_dpi: int = 300
    mineru_effort: str = "medium"


class GlossaryConfig(BaseModel):
    storage: str = "csv"
    scope: str = "chapter"


class PathsConfig(BaseModel):
    workspaces_dir: str = "."


class OutputConfig(BaseModel):
    mono: bool = True
    bilingual: bool = False
    about_page: bool = True
    theme: str = "standard"  # standard | compact | spacious（epub-template-spec §5）


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
