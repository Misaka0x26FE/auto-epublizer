#!/usr/bin/env python3
"""i18n 同步契约工具（中英文档；标准库，离线确定性）。

约定（详见 ``docs/i18n.md``）：

- 英文默认 ``X.md``，中文 ``X.zh.md``（同目录孪生）；
- 派生侧顶部写 ``<!-- i18n: source=X.zh.md sha256=<hex> -->``（方向中立：
  工具读取 ``source=`` 声明的文件并重算哈希比对）；
- 两侧顶部各写语言切换横幅 ``> **English** | [中文](X.zh.md)`` /
  ``> **中文** | [English](X.md)``。

用法：

    python scripts/i18n.py --check              # 全部孪生：戳新鲜 + 横幅存在
    python scripts/i18n.py --links              # 全部 md 相对链接：可解析 + 语言一致
    python scripts/i18n.py --finalize <file>    # 写入/更新一对的戳与横幅
    python scripts/i18n.py --audit              # 列出无孪生的 md（人工复核豁免）
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 不参与扫描的目录（构建产物/依赖/二进制参考）
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "dist",
    "参考",
    "PDFs",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}

_STAMP_RE = re.compile(r"^<!--\s*i18n:\s*source=(\S+)\s+sha256=([0-9a-f]{64})\s*-->$")
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_ZH_SUFFIX = ".zh.md"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _excluded(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in EXCLUDE_DIRS for part in rel.parts)


def iter_md(root: Path, *, exclude: bool = True) -> list[Path]:
    """按路径排序的全部 ``*.md``（默认排除构建/依赖目录）。"""
    out = [p for p in root.rglob("*.md") if not exclude or not _excluded(p, root)]
    return sorted(out)


def _pair_of(path: Path) -> tuple[Path, Path]:
    """返回 ``(en, zh)`` 孪生路径（文件可不存在）。"""
    if path.name.endswith(_ZH_SUFFIX):
        zh = path
        en = path.with_name(path.name[: -len(_ZH_SUFFIX)] + ".md")
    else:
        en = path
        zh = path.with_name(path.stem + _ZH_SUFFIX)
    return en, zh


def parse_stamp(text: str) -> tuple[str, str] | None:
    """解析首个 i18n 戳行 → ``(source_name, sha256)``；无则 None。"""
    for line in text.splitlines()[:8]:
        m = _STAMP_RE.match(line.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def _strip_i18n_header(text: str) -> str:
    """去掉顶部连续的 i18n 戳行与语言横幅行（及其后空行）。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if _STAMP_RE.match(s):
            i += 1
            continue
        if s.startswith(">") and ("[中文](" in s or "[English](" in s):
            i += 1
            continue
        if s == "" and i > 0:
            i += 1
            continue
        break
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    return "\n".join(lines[i:])


def _banner(path: Path) -> str:
    en, zh = _pair_of(path)
    if path.name.endswith(_ZH_SUFFIX):
        return f"> **中文** | [English]({en.name})"
    return f"> **English** | [中文]({zh.name})"


def _has_banner(text: str, path: Path) -> bool:
    en, zh = _pair_of(path)
    sibling = en.name if path.name.endswith(_ZH_SUFFIX) else zh.name
    for line in text.splitlines()[:8]:
        if sibling in line and ("[中文](" in line or "[English](" in line):
            return True
    return False


def _has_twin(path: Path) -> bool:
    en, zh = _pair_of(path)
    return en.exists() and zh.exists()


def check_stamps(root: Path = REPO_ROOT) -> list[str]:
    """校验全部 ``*.zh.md`` 孪生：英文存在、戳新鲜、两侧横幅存在。"""
    errors: list[str] = []
    for zh in iter_md(root):
        if not zh.name.endswith(_ZH_SUFFIX):
            continue
        en, _ = _pair_of(zh)
        rel = zh.relative_to(root)
        if not en.exists():
            errors.append(f"{rel}: 缺少英文孪生 {en.name}")
            continue
        text_en = en.read_text(encoding="utf-8")
        text_zh = zh.read_text(encoding="utf-8")
        stamp = parse_stamp(text_en) or parse_stamp(text_zh)
        if stamp is None:
            errors.append(f"{en.relative_to(root)}: 缺少 i18n 戳")
        else:
            src_name, digest = stamp
            src = zh.parent / src_name
            if not src.is_file():
                errors.append(f"{en.relative_to(root)}: 戳声明的源不存在 {src_name}")
            elif sha256_file(src) != digest:
                errors.append(
                    f"{src.relative_to(root)}: 内容已变，英文版过期（需重译并 --finalize）"
                )
        if not _has_banner(text_en, en):
            errors.append(f"{en.relative_to(root)}: 缺少语言横幅")
        if not _has_banner(text_zh, zh):
            errors.append(f"{zh.relative_to(root)}: 缺少语言横幅")
    return errors


def _strip_fences(text: str) -> str:
    """去掉 ``` 围栏代码块内容（避免示例路径误判为链接）。"""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _side(path: Path, other: Path) -> bool:
    """``other`` 是否为 ``path`` 的对侧（语言不同、同逻辑文档）。"""
    return path.name != other.name and path.parent == other.parent


def check_links(root: Path = REPO_ROOT) -> list[str]:
    """校验全部 md 相对链接：可解析 + 同语言互链（已译文档）。"""
    errors: list[str] = []
    for md in iter_md(root):
        rel = md.relative_to(root)
        text = _strip_fences(_strip_i18n_header(md.read_text(encoding="utf-8")))
        linker_is_zh = md.name.endswith(_ZH_SUFFIX)
        linker_translated = _has_twin(md)
        for m in _LINK_RE.finditer(text):
            raw = m.group(1).strip()
            if raw.startswith(("http://", "https://", "mailto:", "#", "<")):
                continue
            target = raw.split("#", 1)[0].strip()
            if not target or not target.lower().endswith(".md"):
                continue
            resolved = (md.parent / target).resolve()
            try:
                tgt_rel = resolved.relative_to(root.resolve())
            except ValueError:
                tgt_rel = None
            if not resolved.exists():
                errors.append(f"{rel}: 链接断裂 → {target}")
                continue
            if not linker_translated:
                continue  # 单语文件（plans/THIRD_PARTY 等）豁免语言规则
            if tgt_rel is None:
                continue  # 链接指向仓库外（存在即可，不做语言规则）
            en, zh = _pair_of(resolved)
            target_translated = en.exists() and zh.exists()
            if not target_translated:
                continue
            target_is_zh = resolved.name.endswith(_ZH_SUFFIX)
            if linker_is_zh and not target_is_zh:
                errors.append(f"{rel}: 中文文档应链 {tgt_rel.with_name(zh.name)}（当前 {target}）")
            if not linker_is_zh and target_is_zh:
                errors.append(f"{rel}: 英文文档应链 {tgt_rel.with_name(en.name)}（当前 {target}）")
    return errors


def audit_unpaired(root: Path = REPO_ROOT) -> list[str]:
    """列出无孪生的 md（人工复核豁免；含历史计划等）。"""
    return [str(p.relative_to(root)) for p in iter_md(root) if not _has_twin(p)]


def finalize(file: Path) -> None:
    """写入/更新一对孪生的 i18n 戳（派生侧）与语言横幅（两侧）。"""
    en, zh = _pair_of(file)
    if not en.is_file() or not zh.is_file():
        raise SystemExit(f"孪生缺失：{en} / {zh}")
    # 先规范化中文源（补横幅），再以其最终内容计算哈希
    zh.write_text(
        f"{_banner(zh)}\n\n{_strip_i18n_header(zh.read_text(encoding='utf-8'))}\n",
        encoding="utf-8",
    )
    digest = sha256_file(zh)
    en.write_text(
        f"<!-- i18n: source={zh.name} sha256={digest} -->\n"
        f"{_banner(en)}\n\n"
        f"{_strip_i18n_header(en.read_text(encoding='utf-8'))}\n",
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2
    mode = args[0]
    if mode == "--check":
        errors = check_stamps()
    elif mode == "--links":
        errors = check_links()
    elif mode == "--audit":
        for item in audit_unpaired():
            print(item)
        return 0
    elif mode == "--finalize":
        for name in args[1:]:
            finalize(Path(name).resolve())
        print(f"已完成 {len(args) - 1} 对")
        return 0
    else:
        print(f"未知参数：{mode}", file=sys.stderr)
        return 2
    if errors:
        print(f"发现 {len(errors)} 个问题：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
