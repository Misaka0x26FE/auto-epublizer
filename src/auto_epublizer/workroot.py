"""长期多书工作根（work root）脚手架生成（issue #30 §1–§3）。

agent 按模板一键生成标准长期工作区：复制仓库内 ``template/work-root/`` 骨架
（AGENTS.md 规范 / config.example.yaml / README.md + ``inbox`` ``sources``
``workspaces`` ``docs`` ``references``）。**template/work-root/ 是唯一权威模板**，
本模块只做确定性复制，不内嵌第二份内容（避免漂移）。

配套的用户说明（各组件功能 + 使用方式）见
``skills/auto-epublizer/references/work-root.md``；生成后的 ``README.md`` 也自带一份。
"""

from __future__ import annotations

import shutil
from pathlib import Path


class WorkRootError(RuntimeError):
    """工作根生成失败（模板缺失/目标非法）。"""


def template_dir() -> Path:
    """仓库内模板目录 ``template/work-root/``（相对本包上溯到仓库根）。"""
    return Path(__file__).resolve().parents[2] / "template" / "work-root"


def create_work_root(target: str | Path, *, force: bool = False) -> dict[str, object]:
    """在 ``target`` 生成标准长期工作区骨架。

    - 源：仓库内 ``template/work-root/``（缺失则报错，提示模板未随仓库提供）；
    - 已存在且非空时**只补缺失**（不覆盖）；``force=True`` 才覆盖同名文件；
    - 目标存在但不是目录 → 报错。
    返回 ``{"dir", "created": [...相对路径], "skipped": [...]}``。
    """
    src = template_dir()
    if not src.is_dir():
        raise WorkRootError(f"未找到工作根模板：{src}（请确认仓库内含 template/work-root/）")
    dest_root = Path(target).expanduser()
    if dest_root.exists() and not dest_root.is_dir():
        raise WorkRootError(f"目标已存在且不是目录：{dest_root}")

    created: list[str] = []
    skipped: list[str] = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        dest = dest_root / rel
        if path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        rel_s = rel.as_posix()
        if dest.exists() and not force:
            skipped.append(rel_s)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        created.append(rel_s)
    return {"dir": str(dest_root), "created": created, "skipped": skipped}
