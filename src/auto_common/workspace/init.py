"""工作区初始化：创建目录骨架、导入源文件、计算 source_sha256、原子提交 publication.json。"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..config import Config
from .models import SCHEMA_VERSION, ConfigSnapshot, Publication, PublicationMeta
from .store import RunStore, atomic_write_json, read_json, slugify, source_sha256


class InitError(ValueError):
    """工作区初始化失败。"""


def init_workspace(
    input_path: str | Path,
    *,
    config: Config | None = None,
    workspace_dir: str | Path | None = None,
    target_language: str | None = None,
    references: Sequence[str | Path] | None = None,
) -> RunStore:
    """初始化一个工作区并返回其 RunStore。

    publication.json 是初始化成功的最终标志：目录骨架与账本先落盘，最后原子提交。
    """
    source = Path(input_path)
    if not source.is_file():
        raise InitError(f"源文件不存在：{source}")

    cfg = config or Config()
    lang = target_language or cfg.language.target
    slug = slugify(source.name)
    root = Path(workspace_dir or cfg.paths.workspaces_dir)
    ws_dir = root / slug

    store = RunStore(ws_dir, create=True)
    if store.exists():
        raise InitError(f"工作区已存在：{ws_dir}（如需重建请先移走）")

    store.ensure_skeleton()

    source_target = store.source_dir / source.name
    shutil.copy2(source, source_target)

    digest = source_sha256(source_target)

    for ref in references or []:
        ref_path = Path(ref)
        if ref_path.is_file():
            shutil.copy2(ref_path, store.references_dir / "user" / ref_path.name)
        elif ref_path.is_dir():
            dst = store.references_dir / "user" / ref_path.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(ref_path, dst)

    pub = Publication(
        schema_version=SCHEMA_VERSION,
        slug=slug,
        meta=PublicationMeta(
            title=Path(source.stem).name,
            source=str(source_target.relative_to(store.dir)),
            source_sha256=digest,
            target_language=lang,
        ),
        config=ConfigSnapshot(
            bilingual=cfg.pipeline.bilingual,
            target_language=lang,
        ),
        units=[],
    )
    store.save_publication(pub)
    store.log_event(
        "run_initialized",
        input_path=str(source),
        title=pub.meta.title,
        source_sha256=digest,
        target_lang=lang,
    )
    return store


def update_meta(store: RunStore, **fields: Any) -> Publication:
    """更新 publication 元数据（缺省保留），并原子写回。

    注意：state_lock 内不得再调用 load_publication/save_publication（二者会再次 flock
    同一锁文件导致死锁），此处用 read_json / atomic_write_json 直接读写。
    """
    with store.state_lock():
        pub = Publication.model_validate(read_json(store.publication_path))
        for key, value in fields.items():
            if value is not None and hasattr(pub.meta, key):
                setattr(pub.meta, key, value)
        atomic_write_json(store.publication_path, pub.model_dump(mode="json"))
    return pub
