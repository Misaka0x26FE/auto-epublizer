"""工作区权威数据模型：publication.json 的 schema。

publication.json 是初始化成功的最终标志与唯一真相：DC 元数据 + 配置快照 + 内容树
（units 列表，各带状态机）。派生状态先落盘，最后原子提交本文件。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"

# 单元状态机
STATUS_PENDING = "pending"
STATUS_SPLIT = "split"
STATUS_ANALYZED = "analyzed"
STATUS_TRANSLATED = "translated"
STATUS_ALIGNED = "aligned"
STATUS_REVIEWED = "reviewed"
STATUS_BUILT = "built"

UNIT_STATES = (
    STATUS_PENDING,
    STATUS_SPLIT,
    STATUS_ANALYZED,
    STATUS_TRANSLATED,
    STATUS_ALIGNED,
    STATUS_REVIEWED,
    STATUS_BUILT,
)

# 允许的单元类型（对应出版物四层结构与辅文类型）
UNIT_KINDS = (
    "cover",
    "titlepage",
    "copyright",
    "dedication",
    "foreword",
    "preface",
    "toc",
    "chapter",
    "section",
    "afterword",
    "appendix",
    "notes",
    "bibliography",
    "index",
    "glossary",
)


class Identifier(BaseModel):
    isbn: str | None = None
    doi: str | None = None
    uri: str | None = None


class PublicationMeta(BaseModel):
    """DC 元数据；source_sha256 绑定源内容身份。"""

    title: str = ""
    title_translated: str | None = None
    creator: str | None = None
    contributors: list[str] = Field(default_factory=list)
    translator: str | None = None
    language: str = ""  # 源语言（auto 时由 analyze 检测后回填）
    target_language: str = "zh-CN"
    genre: str | None = None  # 体裁（auto 时由 analyze 判定后回填）
    publisher: str | None = None
    date: str | None = None
    identifier: Identifier = Field(default_factory=Identifier)
    source: str = ""  # 相对 source/ 的主文件路径
    source_sha256: str = ""  # 源内容身份（64 位十六进制）
    rights: str | None = None
    description: str | None = None
    subjects: list[str] = Field(default_factory=list)


class ConfigSnapshot(BaseModel):
    """init 时固化的关键运行配置，续跑时优先使用，避免配置漂移。"""

    engine_profile: str = "openai-compatible"
    bilingual: bool = False
    polish: bool = False
    review: bool = True
    target_language: str = "zh-CN"


class Unit(BaseModel):
    """内容树节点：一个稳定 ID 对应一个可翻译/可构建的最小单元。"""

    id: str
    kind: str = "chapter"
    title: str = ""
    status: str = STATUS_PENDING
    meta: dict[str, Any] = Field(default_factory=dict)


class Publication(BaseModel):
    schema_version: str = SCHEMA_VERSION
    slug: str
    meta: PublicationMeta = Field(default_factory=PublicationMeta)
    config: ConfigSnapshot = Field(default_factory=ConfigSnapshot)
    units: list[Unit] = Field(default_factory=list)

    def unit(self, unit_id: str) -> Unit | None:
        for u in self.units:
            if u.id == unit_id:
                return u
        return None

    def set_unit_status(self, unit_id: str, status: str) -> None:
        for u in self.units:
            if u.id == unit_id:
                u.status = status
                return
        raise KeyError(unit_id)
