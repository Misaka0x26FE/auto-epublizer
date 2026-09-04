"""pydantic 配置模型：对齐 docs/configuration.md 的目标 schema。

API Key 只从环境变量读取（``llm.api_key_env`` 指向的变量），禁止写入配置文件、
源码、测试或提交。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

TierName = Literal["strong", "cheap", "fast"]


class TierConfig(BaseModel):
    model: str
    options: dict[str, Any] = Field(default_factory=dict)


class LanguageConfig(BaseModel):
    source: str = "auto"
    target: str = "zh-CN"
    genre: str = "auto"


class LLMConfig(BaseModel):
    provider: str = "openai-compatible"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    timeout: float = 600.0
    max_retries: int = 4
    vision_model: str | None = None  # 多模态模型（扫描 PDF 视觉兜底用；None=未配置）
    tiers: dict[str, TierConfig] = Field(
        default_factory=lambda: {
            "strong": TierConfig(model="deepseek-v4-pro", options={"thinking": True}),
            "cheap": TierConfig(model="deepseek-v4-flash", options={"thinking": True}),
            "fast": TierConfig(model="deepseek-v4-flash"),
        }
    )

    def api_key(self) -> str | None:
        import os

        return os.environ.get(self.api_key_env)


class SegmentConfig(BaseModel):
    max_chars_per_segment: int = 1200
    max_chars_per_batch: int = 1800
    rolling_context_segments: int = 6


class PipelineConfig(BaseModel):
    translate: bool = True
    polish: bool = False
    review: bool = True
    book_understanding: bool = True
    prescan_concurrency: int = 4
    bilingual: bool = False
    bilingual_order: Literal["target_first", "source_first"] = "target_first"
    bilingual_preserve_source_style: bool = False
    annotation_alignment: bool = True


class ReviewConfig(BaseModel):
    enabled: bool = True
    concurrency: int = 4
    output_retries: int = 2


class EvidenceConfig(BaseModel):
    enabled: bool = True
    tier: TierName = "strong"
    max_rounds: int = 2


class ArbitrationConfig(BaseModel):
    enabled: bool = True


class FixLoopConfig(BaseModel):
    enabled: bool = True
    max_rounds: int = 2
    clean_confirmations: int = 2


class EpubcheckConfig(BaseModel):
    # pydantic v2 默认值不走 field_validator，必须显式 validate_default 展开 `~`
    jar: str = Field(default="~/.cache/epubcheck.jar", validate_default=True)
    strict: bool = True

    @field_validator("jar")
    @classmethod
    def expand_home(cls, value: str) -> str:
        return str(Path(value).expanduser())


class QCConfig(BaseModel):
    gates: list[str] = Field(default_factory=lambda: ["g0", "g1", "g2", "g3", "g4", "g5"])
    length_ratio: dict[str, float] = Field(
        default_factory=lambda: {"too_short": 0.30, "too_long": 3.0}
    )
    error_rate_threshold: float = 0.0001
    align_retry_limit: int = 2
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    arbitration: ArbitrationConfig = Field(default_factory=ArbitrationConfig)
    fix_loop: FixLoopConfig = Field(default_factory=FixLoopConfig)
    autofix: bool = False
    epubcheck: EpubcheckConfig = Field(default_factory=EpubcheckConfig)


class PDFConfig(BaseModel):
    backend: str = "auto"
    ocr: str = "auto"
    page_dpi: int = 300
    vision_llm_fallback: bool = True
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
    llm: LLMConfig = Field(default_factory=LLMConfig)
    segment: SegmentConfig = Field(default_factory=SegmentConfig)
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
