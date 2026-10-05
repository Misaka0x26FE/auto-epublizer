"""install-skills.sh 的合规校验门（skills.sh / Agent Skills）离线回归。"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-skills.sh"


def test_install_skills_check_passes() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "name=auto-epublizer" in result.stdout
