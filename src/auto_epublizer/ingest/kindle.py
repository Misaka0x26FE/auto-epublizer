"""Kindle 容器支持（``.azw3`` / ``.azw`` / ``.mobi``，issue #30 §4.1）。

经 calibre 的 ``ebook-convert`` 转为临时 EPUB，再走既有 EPUB 读取链。转换器缺失或失败时
给出**明确中文提示**（引导用户先自查），不静默失败。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

KINDLE_EXTS = {".azw3", ".azw", ".mobi"}


class KindleError(RuntimeError):
    """Kindle 格式无法处理（缺转换器 / 转换失败）。"""


@contextmanager
def as_epub(path: str | Path) -> Iterator[Path]:
    """把 Kindle 文件转成临时 EPUB；退出时自动清理目录。"""
    src = Path(path)
    exe = shutil.which("ebook-convert")
    if exe is None:
        raise KindleError(
            f"Kindle 格式（{src.suffix}）需要 calibre 的 ebook-convert；未安装——"
            "请先用 calibre 转为 EPUB/PDF 后重试"
        )
    with tempfile.TemporaryDirectory(prefix="auto-epublizer-kindle-") as tmp:
        out = Path(tmp) / (src.stem + ".epub")
        try:
            proc = subprocess.run(
                [exe, str(src), str(out)],
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise KindleError(f"ebook-convert 无法执行：{e}") from e
        if proc.returncode != 0 or not out.is_file():
            detail = (proc.stderr or proc.stdout or "").strip()[:300]
            raise KindleError(f"ebook-convert 转换失败（退出码 {proc.returncode}）：{detail}")
        yield out
