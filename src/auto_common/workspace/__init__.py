"""工作区：publication.json 权威索引 + RunStore（原子写/锁/sha256 绑定/账本/快照）。"""

from __future__ import annotations

from .init import InitError, init_workspace, update_meta
from .models import (
    STATUS_ALIGNED,
    STATUS_ANALYZED,
    STATUS_BUILT,
    STATUS_PENDING,
    STATUS_REVIEWED,
    STATUS_SPLIT,
    STATUS_TRANSLATED,
    UNIT_KINDS,
    UNIT_STATES,
    ConfigSnapshot,
    Identifier,
    Publication,
    PublicationMeta,
    Unit,
)
from .store import RunStore, atomic_write_json, read_json, slugify, source_sha256

__all__ = [
    "ConfigSnapshot",
    "Identifier",
    "InitError",
    "Publication",
    "PublicationMeta",
    "RunStore",
    "UNIT_KINDS",
    "UNIT_STATES",
    "Unit",
    "STATUS_ALIGNED",
    "STATUS_ANALYZED",
    "STATUS_BUILT",
    "STATUS_PENDING",
    "STATUS_REVIEWED",
    "STATUS_SPLIT",
    "STATUS_TRANSLATED",
    "atomic_write_json",
    "init_workspace",
    "read_json",
    "slugify",
    "source_sha256",
    "update_meta",
]
