# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""CI 强制外部工具门：固定版本的 pandoc / java / epubcheck 缺失时必须失败。

本地开发允许 skip（未装工具时其余测试用替身覆盖），CI 设置
``AUTO_EPUBLIZER_REQUIRE_EXTERNAL=1`` 后本测试把“静默跳过”变成红灯。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from auto_common.config import Config
from auto_epublizer.ingest.pandoc_reader import pandoc_available

REQUIRED = os.environ.get("AUTO_EPUBLIZER_REQUIRE_EXTERNAL") == "1"


@pytest.mark.skipif(not REQUIRED, reason="本地未要求外部工具；CI 用环境变量强制")
def test_pandoc_is_installed() -> None:
    assert pandoc_available(), "CI 必须安装固定版本的 pandoc"


@pytest.mark.skipif(not REQUIRED, reason="本地未要求外部工具；CI 用环境变量强制")
def test_epubcheck_jar_and_java_are_installed() -> None:
    jar = Path(Config().qc.epubcheck.jar).expanduser()
    assert jar.is_file(), f"缺少 epubcheck jar：{jar}"
    assert shutil.which("java"), "缺少 java 运行时"
