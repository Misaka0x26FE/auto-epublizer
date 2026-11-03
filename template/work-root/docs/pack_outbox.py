#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""仅打包真实 CLI 当前放行的指定工作区；不计算第二套 QA 状态。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect(workspace: Path, cli: str) -> tuple[Path, str, bytes]:
    result = subprocess.run(
        [cli, "status", "--workspace", str(workspace), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    status = json.loads(result.stdout)
    current = status["report"]
    if not (
        current.get("released") is True
        and current.get("stale") is False
        and current.get("reason") == "ok"
    ):
        raise ValueError(f"未获当前放行（含过期报告）：{workspace}：{current}")
    report_bytes = (workspace / "report.json").read_bytes()
    report = json.loads(report_bytes)
    if report.get("released") is not True or report.get("released_reason") != "ok":
        raise ValueError(f"报告在检查期间改变或未放行：{workspace}")
    artifact = report.get("artifacts_epub")
    if not isinstance(artifact, str) or not artifact:
        raise ValueError(f"报告缺少精确 artifacts_epub：{workspace}")
    source = Path(artifact)
    if not source.is_absolute():
        source = workspace / source
    source = source.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".epub":
        raise ValueError(f"报告产物不是 EPUB 文件：{source}")
    return source, digest(source), report_bytes


def book_identity(workspace: Path) -> dict:
    """工作区的批次身份：书名/来源摘要/report 绑定；版本由调用方显式给出。"""
    publication = json.loads((workspace / "publication.json").read_text(encoding="utf-8"))
    meta = publication.get("meta") or {}
    return {
        "book": str(meta.get("title") or publication.get("slug") or "").strip(),
        "source": str(meta.get("source") or ""),
        "source_sha256": str(meta.get("source_sha256") or ""),
        "version": str(meta.get("version") or "").strip(),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="整批预检、复制并校验已放行 EPUB；从不覆盖旧批次。"
    )
    parser.add_argument(
        "workspaces", nargs="+", type=Path, help="本批全部工作区目录（包含 publication.json）"
    )
    parser.add_argument("--outbox", type=Path, default=root / "outbox", help="交付根目录")
    parser.add_argument("--batch", required=True, help="新批次名（单个目录名）")
    parser.add_argument("--cli", default="auto-epublizer", help="真实 auto-epublizer 可执行路径")
    parser.add_argument(
        "--version",
        default="",
        help="本批交付版本（整批共用）；缺省取各工作区 meta.version，仍为空则记为未定版本",
    )
    args = parser.parse_args()
    try:
        if (
            not args.batch
            or args.batch in {".", ".."}
            or Path(args.batch).name != args.batch
            or "\\" in args.batch
        ):
            raise ValueError("批次名必须是单个目录名")
        batch = args.outbox.resolve() / args.batch
        archived = args.outbox.resolve() / ".archive" / args.batch
        if archived.exists() or archived.is_symlink():
            raise ValueError(f"同名批次已归档，拒绝新建：{archived}")
        if batch.exists() or batch.is_symlink():
            state = (
                "完整批次，拒绝覆盖（未复制）"
                if (batch / "MANIFEST.md").is_file()
                else "中断/旧批次，拒绝覆盖（未复制）"
            )
            raise ValueError(f"{state}：{batch}")
        workspaces = [p.resolve(strict=True) for p in args.workspaces]
        if len(set(workspaces)) != len(workspaces):
            raise ValueError("工作区重复；整批未复制")
        entries = [(ws, *inspect(ws, args.cli)) for ws in workspaces]
        names = [source.name.casefold() for _, source, _, _ in entries]
        if len(set(names)) != len(names):
            raise ValueError("产物文件名冲突；请先在工作区解决命名，整批未复制")
        # 整批预检完成后才创建目录；异常保留无 MANIFEST 的现场，绝不冒充完整批次。
        batch.mkdir(parents=True, exist_ok=False)
        epubs = batch / "epub"
        epubs.mkdir()
        for _, source, _, _ in entries:
            with source.open("rb") as src, (epubs / source.name).open("xb") as dest:
                shutil.copyfileobj(src, dest)
        for ws, source, expected, report_bytes in entries:
            if digest(epubs / source.name) != expected or digest(source) != expected:
                raise ValueError(f"复制后 SHA256 不一致：{source}；批次未完成")
            if inspect(ws, args.cli) != (source, expected, report_bytes):
                raise ValueError(f"复制期间状态/报告/产物变化：{ws}；批次未完成")
        books = []
        lines = ["# 交付清单", "", "全部文件经真实 status 当前放行与复制后 SHA256 核对。", ""]
        for ws, source, expected, report_bytes in entries:
            identity = book_identity(ws)
            version = args.version.strip() or identity["version"]
            books.append(
                {
                    "book": identity["book"],
                    "version": version,
                    "workspace": str(ws),
                    "source": identity["source"],
                    "source_sha256": identity["source_sha256"],
                    "artifacts": [
                        {
                            "path": "epub/" + source.name,
                            "sha256": expected,
                            "bytes": (epubs / source.name).stat().st_size,
                        }
                    ],
                    "report": {
                        "sha256": hashlib.sha256(report_bytes).hexdigest(),
                        "released": True,
                        "released_reason": "ok",
                    },
                    "pdf": None,
                }
            )
            lines.extend(
                [
                    "| 字段 | 值 |",
                    "| --- | --- |",
                    f"| 书名 | {identity['book']} |",
                    f"| 版本 | {version or '未定'} |",
                    "",
                    f"- 文件：{json.dumps('epub/' + source.name, ensure_ascii=False)}",
                    f"  - 工作区：{json.dumps(str(ws), ensure_ascii=False)}",
                    f"  - 报告产物：{json.dumps(str(source), ensure_ascii=False)}",
                    f"  - SHA256：`{expected}`",
                    "",
                ]
            )
        manifest = {
            "schema_version": "auto-epublizer/batch/v1",
            "batch": args.batch,
            "books": books,
        }
        # 机器清单先落盘，MANIFEST.md 最后作为完成标记：中途失败只会留下未完成批次。
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=batch, prefix=".batch-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(batch / "batch.json")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=batch, prefix=".MANIFEST-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write("\n".join(lines) + "\n")
        temporary.replace(batch / "MANIFEST.md")
        print(f"已完整复制并校验 {len(entries)} 件：{batch}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(f"打包失败：{detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
