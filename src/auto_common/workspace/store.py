"""RunStore：工作区状态的一致性读写。

- 同目录临时文件 + ``os.replace`` 原子写；
- ``source_sha256`` 绑定源内容身份，拒绝同名不同内容静默复用状态；
- 多级 flock（run/state/event）隔离长流程与短状态读写；
- ``events.jsonl`` 追加式行为账本；
- ``usage.json`` 用量账本，一次运行增量只合并一次；
- 导出前冻结一致快照（ExportSnapshot）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import STATUS_PENDING, Publication

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceIdentityError(ValueError):
    """源内容身份与工作区状态不一致。"""


def slugify(name: str) -> str:
    """把文件名/书名转换为适合做目录名的稳定 ASCII slug。"""
    stem = Path(name).stem.lower()
    s = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return s or "book"


def source_sha256(path: str | Path) -> str:
    """流式计算源文件 SHA-256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: str | Path, data: Any) -> None:
    """通过同目录临时文件原子写入格式化 JSON。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, target)


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class RunStore:
    """绑定一个工作区目录，负责 publication.json 与账本的原子读写。"""

    def __init__(self, workspace_dir: str | Path, *, create: bool = True) -> None:
        self.dir = Path(workspace_dir)
        if create:
            self.dir.mkdir(parents=True, exist_ok=True)

    # ── 路径 ──────────────────────────────────────────────────────────────
    @property
    def publication_path(self) -> Path:
        return self.dir / "publication.json"

    @property
    def event_log_path(self) -> Path:
        return self.dir / "events.jsonl"

    @property
    def usage_path(self) -> Path:
        return self.dir / "usage.json"

    @property
    def progress_path(self) -> Path:
        return self.dir / ".progress.json"

    @property
    def report_path(self) -> Path:
        return self.dir / "report.json"

    @property
    def source_dir(self) -> Path:
        return self.dir / "source"

    @property
    def structured_dir(self) -> Path:
        return self.dir / "structured"

    @property
    def analysis_dir(self) -> Path:
        return self.dir / "analysis"

    @property
    def translation_dir(self) -> Path:
        return self.dir / "translation"

    @property
    def references_dir(self) -> Path:
        return self.dir / "references"

    @property
    def reviews_dir(self) -> Path:
        return self.dir / "reviews"

    @property
    def preprocessing_dir(self) -> Path:
        return self.dir / "preprocessing"

    @property
    def output_dir(self) -> Path:
        return self.dir / "output"

    def unit_structured_path(self, unit_id: str) -> Path:
        return self.structured_dir / unit_id

    def unit_translation_path(self, unit_id: str) -> Path:
        return self.translation_dir / unit_id

    def unit_align_path(self, unit_id: str) -> Path:
        return self.translation_dir / "align" / f"{unit_id}.jsonl"

    def unit_analysis_path(self, unit_id: str) -> Path:
        return self.analysis_dir / "units" / f"{unit_id}.md"

    # ── 锁 ────────────────────────────────────────────────────────────────
    @contextmanager
    def _file_lock(self, name: str) -> Iterator[None]:
        self.dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.dir / name
        with open(lock_path, "a+b") as f:
            if os.name == "nt":  # pragma: no cover - Windows
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def run_lock(self) -> Iterator[None]:
        with self._file_lock(".run.lock"):
            yield

    @contextmanager
    def state_lock(self) -> Iterator[None]:
        with self._file_lock(".state.lock"):
            yield

    @contextmanager
    def event_lock(self) -> Iterator[None]:
        with self._file_lock(".events.lock"):
            yield

    # ── 存在性与初始化 ────────────────────────────────────────────────────
    def exists(self) -> bool:
        return self.publication_path.is_file()

    def require_initialized(self) -> Publication:
        if not self.exists():
            raise FileNotFoundError(
                f"工作区尚未初始化（缺少 {self.publication_path}）；请先运行 auto-epublizer init"
            )
        return self.load_publication()

    # ── publication.json ──────────────────────────────────────────────────
    def save_publication(self, pub: Publication) -> None:
        with self.state_lock():
            atomic_write_json(self.publication_path, pub.model_dump(mode="json"))

    def load_publication(self) -> Publication:
        with self.state_lock():
            data = read_json(self.publication_path)
        return Publication.model_validate(data)

    def set_unit_status(self, unit_id: str, status: str) -> None:
        with self.state_lock():
            pub = Publication.model_validate(read_json(self.publication_path))
            pub.set_unit_status(unit_id, status)
            atomic_write_json(self.publication_path, pub.model_dump(mode="json"))

    def set_units(self, units: list[Any]) -> None:
        """把结构化单元清单写入 publication.json.units（保留已存在单元的状态与 rel_path）。"""
        from .models import Unit

        with self.state_lock():
            pub = Publication.model_validate(read_json(self.publication_path))
            existing = {u.id: u for u in pub.units}
            pub.units = []
            for u in units:
                prior = existing.get(u["id"])
                meta = dict(prior.meta) if prior else {}
                if u.get("rel_path"):
                    meta["rel_path"] = u["rel_path"]
                if u.get("region"):
                    meta["region"] = u["region"]
                status = prior.status if prior else STATUS_PENDING
                pub.units.append(
                    Unit(id=u["id"], kind=u["kind"], title=u["title"], status=status, meta=meta)
                )
            atomic_write_json(self.publication_path, pub.model_dump(mode="json"))

    # ── 源身份 ────────────────────────────────────────────────────────────
    def ensure_source_identity(
        self,
        source_path: str | Path,
        *,
        actual_sha256: str | None = None,
    ) -> str:
        """校验输入内容属于当前工作区状态；不一致则拒绝。"""
        actual = actual_sha256 or source_sha256(source_path)
        if not _SHA256_RE.match(actual):
            raise ValueError("源文件 SHA-256 格式无效")
        pub = self.require_initialized()
        expected = pub.meta.source_sha256
        if not _SHA256_RE.match(expected):
            raise SourceIdentityError("现有状态缺少有效 source_sha256；请重新 init")
        if expected != actual:
            raise SourceIdentityError(
                "输入文件内容与工作区不一致（同名不同内容）；请使用原始源文件或重新 init"
            )
        return actual

    # ── 事件账本 ──────────────────────────────────────────────────────────
    def log_event(self, event: str, **data: Any) -> None:
        row = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event": event,
            **data,
        }
        with self.event_lock():
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.event_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def save_qa(self, report: dict[str, Any]) -> None:
        atomic_write_json(self.report_path, report)

    def read_events(self) -> list[dict[str, Any]]:
        if not self.event_log_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with open(self.event_log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    # ── 用量账本 ──────────────────────────────────────────────────────────
    def load_usage(self) -> dict[str, Any]:
        if not self.usage_path.is_file():
            return {
                "totals": {},
                "by_tier": {},
                "by_stage": {},
            }
        with self.state_lock():
            return read_json(self.usage_path)

    def merge_usage(
        self, increment: dict[str, Any], *, run_id: str | None = None
    ) -> dict[str, Any]:
        """把一次运行增量合并进历史累计用量。

        ``run_id`` 用于幂等：同一 run_id 只合并一次，重试/续跑不重复计费。
        """
        from ..llm.usage import merge_usage_summaries

        with self.state_lock():
            current = (
                read_json(self.usage_path)
                if self.usage_path.is_file()
                else {"by_tier": {}, "by_stage": {}}
            )
            merged_runs = list(current.get("merged_runs", []))
            if run_id:
                if run_id in merged_runs:
                    return current
                merged_runs.append(run_id)
            merged = merge_usage_summaries(
                current
                or {
                    "by_tier": {},
                    "by_stage": {},
                },
                increment,
            )
            merged["merged_runs"] = merged_runs
            atomic_write_json(self.usage_path, merged)
            return merged

    # ── 导出快照 ──────────────────────────────────────────────────────────
    def create_export_snapshot(self, *, actual_sha256: str) -> Publication:
        """在短状态锁内冻结 publication.json 一致快照。"""
        with self.state_lock():
            data = read_json(self.publication_path)
        pub = Publication.model_validate(data)
        if pub.meta.source_sha256 != actual_sha256:
            raise SourceIdentityError("源内容身份与工作区不一致")
        return pub

    # ── 目录骨架 ──────────────────────────────────────────────────────────
    def ensure_skeleton(self) -> None:
        for sub in (
            "source",
            "structured/raw",
            "structured/media",
            "analysis/units",
            "translation/align",
            "references/user",
            "references/web",
            "reviews",
            "preprocessing",
            "output",
        ):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)


class ExportSnapshot:
    """导出专用的内存只读快照。"""

    def __init__(self, publication: Publication) -> None:
        self._publication = publication.model_copy(deep=True)

    def publication(self) -> Publication:
        return self._publication.model_copy(deep=True)
