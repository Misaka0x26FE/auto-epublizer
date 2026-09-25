"""统一术语库/知识库编排：持久化目录解析 + git 持续维护 + 命令实现。

- 目录解析优先级：``--dir`` > 环境变量 ``AUTO_EPUBLIZER_HOME`` > 配置
  ``paths.knowledge_dir`` > 默认 ``~/Documents/auto-epublizer``。
- git：``init`` / ``commit`` / ``push``（本地确定性操作；失败仅告警，不阻断术语合并）；
  提交时若环境未配置 git 身份则注入兜底身份，保证无身份机器上也能确定性提交。
- 内容：术语表 CSV 的读写/合并/导出复用 ``auto_translator.glossary.store``（纯函数）；
- 裁决：跨书冲突外置到 ``conflicts.jsonl`` 待 agent 裁决（单 LLM 原则，CLI 不裁决）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from auto_common.config import Config
from auto_common.workspace import RunStore
from auto_translator.glossary import (
    GlossaryEntry,
    export_for_workspace,
    load_glossary_csv,
    load_legacy_category_csv,
    load_store_csv,
    merge_workspace_glossary,
    read_store_conflicts,
    save_store_csv,
    store_stats,
    write_store_conflicts,
    write_workspace_terms,
)

DEFAULT_STORE_DIRNAME = "auto-epublizer"

_STORE_README = """# auto-epublizer 统一术语库 / 知识库

本目录由 `auto-epublizer` 的 **agent** 自行维护，跨工作区（跨书）复用，避免重复考据与
重复裁决。默认作为**私有** git 仓库持续维护；条件允许时推送到 GitHub 等托管平台跨设备同步。

## 目录结构

- `terminology.csv` —— 统一术语表（列 = 工作区 `glossary.csv` + 溯源列
  `src_lang,tgt_lang,book`）；键为 `(src_lang, tgt_lang, source)`。
- `conflicts.jsonl` —— 跨书术语冲突账本（append-only，待 agent 裁决）。
- `knowledge/` —— 知识库（agent 自由撰写的 markdown：人物考据、体例决策、经验）。

## 用法

```bash
auto-epublizer knowledge path                      # 查看本目录与覆盖来源
auto-epublizer knowledge export --workspace <ws>   # 同语对已确认术语 → preprocessing/terms.csv
auto-epublizer knowledge import --workspace <ws>   # 工作区 glossary.csv → 统一库（合并 + 自动提交）
auto-epublizer knowledge status                    # 统计 + git 状态
auto-epublizer knowledge push                      # 推送到远端（跨设备同步）
```

**裁决**：`conflicts.jsonl` 与 `terminology.csv` 中同一键出现多个译法时，由 agent 阅读
证据后直接编辑 `terminology.csv`（保留一个、删除/清空其余），未裁决计数随之归零。
"""

_KNOWLEDGE_INDEX = """# 知识库目录（INDEX）

本目录由 agent 自行维护：人物/地名考据、机构与专名决议、体例与风格决策、踩坑经验。
每篇一主题，文件名用 `YYYY-MM-DD-<主题>.md`，正文建议含「判据 / 处置 / 验证」三段。
在下方登记条目，便于后续工作区快速检索。

| 文件 | 主题 | 关联书目/语对 |
|---|---|---|
| （示例）2026-09-25-napoleon-name.md | 拿破仑译名统一 | en->zh-CN |
"""

_STORE_GITIGNORE = """# 运行时/临时/系统文件
*.tmp
.DS_Store
__pycache__/
*.py[cod]
"""


def _default_store_dir() -> Path:
    return Path.home() / "Documents" / DEFAULT_STORE_DIRNAME


def resolve_store_dir(config: Config | None = None, *, override: str | None = None) -> Path:
    """解析统一库目录：override > 环境变量 > 配置 > 默认。"""
    if override:
        return Path(override).expanduser()
    env = os.environ.get("AUTO_EPUBLIZER_HOME")
    if env:
        return Path(env).expanduser()
    if config is not None and config.paths.knowledge_dir:
        return Path(config.paths.knowledge_dir).expanduser()
    return _default_store_dir()


def resolve_remote(config: Config | None = None, *, override: str | None = None) -> str:
    """解析统一库 git 远端：override > 环境变量 > 配置。"""
    if override:
        return override
    env = os.environ.get("AUTO_EPUBLIZER_REMOTE")
    if env:
        return env
    if config is not None and config.paths.knowledge_remote:
        return config.paths.knowledge_remote
    return ""


def _git_env() -> dict[str, str]:
    """注入兜底 git 身份（仅当环境未提供时），保证无身份机器上也能提交。"""
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "auto-epublizer")
    env.setdefault("GIT_AUTHOR_EMAIL", "auto-epublizer@localhost")
    env.setdefault("GIT_COMMITTER_NAME", "auto-epublizer")
    env.setdefault("GIT_COMMITTER_EMAIL", "auto-epublizer@localhost")
    return env


def git_available() -> bool:
    return shutil.which("git") is not None


def _git(store_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(store_dir), *args],
        capture_output=True,
        text=True,
        env=_git_env(),
        check=False,
    )


def is_git_repo(store_dir: Path) -> bool:
    if not (store_dir / ".git").exists():
        return False
    return _git(store_dir, "rev-parse", "--is-inside-work-tree").returncode == 0


def git_state(store_dir: Path) -> dict:
    """store 的 git 状态快照（只读，不发网络请求）。"""
    if not is_git_repo(store_dir):
        return {"repo": False, "dirty": False, "remote": None, "branch": "", "last_commit": ""}
    dirty = bool(_git(store_dir, "status", "--porcelain").stdout.strip())
    remote = _git(store_dir, "remote", "get-url", "origin")
    branch = _git(store_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    last = _git(store_dir, "log", "-1", "--format=%h %s").stdout.strip()
    return {
        "repo": True,
        "dirty": dirty,
        "remote": remote.stdout.strip() if remote.returncode == 0 else None,
        "branch": branch,
        "last_commit": last,
    }


def git_commit(store_dir: Path, message: str) -> tuple[bool, str]:
    """提交 store 全部改动；无改动/非仓库/失败返回 (False, 原因)。"""
    if not is_git_repo(store_dir):
        return False, "非 git 仓库（先运行 knowledge init）"
    _git(store_dir, "add", "-A")
    result = _git(store_dir, "commit", "-q", "-m", message)
    if result.returncode == 0:
        return True, "已提交"
    combined = (result.stdout + result.stderr).strip()
    if "nothing to commit" in combined:
        return False, "无改动"
    return False, combined or "git commit 失败"


def git_push(store_dir: Path, remote: str = "origin") -> tuple[bool, str]:
    """推送当前分支到远端（需要网络与凭据；失败返回原因，不抛异常）。"""
    if not is_git_repo(store_dir):
        return False, "非 git 仓库（先运行 knowledge init）"
    has_remote = _git(store_dir, "remote", "get-url", remote)
    if has_remote.returncode != 0:
        return False, f"未配置远端 {remote}（用 --remote 或 knowledge init --remote 指定）"
    result = _git(store_dir, "push", "-u", remote, "HEAD")
    if result.returncode == 0:
        return True, "已推送"
    return False, (result.stdout + result.stderr).strip() or "git push 失败"


def _ensure_skeleton(store_dir: Path) -> None:
    (store_dir / "knowledge").mkdir(parents=True, exist_ok=True)
    files = {
        store_dir / "README.md": _STORE_README,
        store_dir / ".gitignore": _STORE_GITIGNORE,
        store_dir / "knowledge" / "INDEX.md": _KNOWLEDGE_INDEX,
    }
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    csv_path = store_dir / "terminology.csv"
    if not csv_path.exists():
        save_store_csv(csv_path, [])
    conflicts = store_dir / "conflicts.jsonl"
    if not conflicts.exists():
        conflicts.write_text("", encoding="utf-8")


def knowledge_init(store_dir: Path, *, remote: str = "", push: bool = False) -> dict:
    """创建 store 骨架 + git init + 首次提交；可选配置远端并首推。"""
    store_dir.mkdir(parents=True, exist_ok=True)
    _ensure_skeleton(store_dir)

    initialized = False
    message = "git 不可用，跳过版本维护"
    if git_available():
        if not is_git_repo(store_dir):
            _git(store_dir, "init", "-q", "-b", "main")
        initialized = True
        if remote:
            existing = _git(store_dir, "remote", "get-url", "origin")
            if existing.returncode == 0:
                _git(store_dir, "remote", "set-url", "origin", remote)
            else:
                _git(store_dir, "remote", "add", "origin", remote)
        committed, message = git_commit(store_dir, "chore(knowledge): 初始化统一术语库/知识库")
        pushed = None
        if push and remote:
            ok, push_msg = git_push(store_dir)
            pushed = {"ok": ok, "message": push_msg}
    else:
        committed, pushed = False, None

    return {
        "store": str(store_dir),
        "initialized": initialized,
        "committed": committed,
        "message": message,
        "remote": remote,
        "pushed": pushed,
    }


def _lang_pair(store: RunStore, src_lang: str | None, tgt_lang: str | None) -> tuple[str, str]:
    pub = store.load_publication()
    src = (src_lang or pub.meta.language or "").strip()
    tgt = (tgt_lang or pub.meta.target_language or "").strip()
    if not src:
        raise ValueError(
            "源语言未知（publication.json.meta.language 为 auto 未回写）："
            "请用 --src-lang 显式声明源语言（ISO 639-1，如 en/ru/ja）"
        )
    return src, tgt


def knowledge_import(
    store_dir: Path,
    store: RunStore,
    *,
    src_lang: str | None = None,
    tgt_lang: str | None = None,
    commit: bool = True,
) -> dict:
    """把工作区 glossary.csv 合并进统一库（幂等）+ 冲突外置 + 自动提交。"""
    _ensure_skeleton(store_dir)
    src, tgt = _lang_pair(store, src_lang, tgt_lang)
    pub = store.load_publication()
    glossary_path = store.analysis_dir / "glossary.csv"
    ws_entries = load_glossary_csv(glossary_path)
    store_entries = load_store_csv(store_dir / "terminology.csv")

    result = merge_workspace_glossary(
        store_entries, ws_entries, src_lang=src, tgt_lang=tgt, book=pub.slug
    )
    save_store_csv(store_dir / "terminology.csv", result.entries)
    conflicts_written = write_store_conflicts(store_dir / "conflicts.jsonl", result.conflicts)

    committed, commit_msg = (False, "跳过提交")
    if commit:
        committed, commit_msg = git_commit(
            store_dir,
            f"chore(knowledge): 合并《{pub.slug}》术语（+{result.added} ~{result.updated} "
            f"冲突{conflicts_written}）",
        )

    return {
        "store": str(store_dir),
        "src_lang": src,
        "tgt_lang": tgt,
        "book": pub.slug,
        "merged": len(ws_entries),
        "added": result.added,
        "updated": result.updated,
        "conflicts": conflicts_written,
        "committed": committed,
        "commit_message": commit_msg,
    }


def _load_any_glossary(path: Path) -> list[GlossaryEntry]:
    """读取任意术语 CSV：表头含 category 且无 type 视为旧案例格式。"""
    first_line = path.read_text(encoding="utf-8").splitlines()[:1]
    header = first_line[0].lower() if first_line else ""
    if "category" in header and "type" not in header:
        return load_legacy_category_csv(path)
    return load_glossary_csv(path)


def knowledge_import_file(
    store_dir: Path,
    csv_path: str | Path,
    *,
    src_lang: str,
    tgt_lang: str,
    book: str,
    status: str | None = None,
    commit: bool = True,
) -> dict:
    """把任意术语 CSV 导入统一库（历史项目不是工作区时的确定性入口）。

    - 自动识别旧案例格式（``category,source,target,note``）与标准格式；
    - ``status`` 可强制覆盖条目态（如历史建议统一为 ``seed``）；
    - 幂等合并 + 冲突外置 + 自动 git 提交。
    """
    _ensure_skeleton(store_dir)
    p = Path(csv_path)
    if not p.is_file():
        raise ValueError(f"术语 CSV 不存在：{p}")
    entries = _load_any_glossary(p)
    if status:
        for entry in entries:
            entry.status = status
    store_entries = load_store_csv(store_dir / "terminology.csv")
    result = merge_workspace_glossary(
        store_entries, entries, src_lang=src_lang, tgt_lang=tgt_lang, book=book
    )
    save_store_csv(store_dir / "terminology.csv", result.entries)
    conflicts_written = write_store_conflicts(store_dir / "conflicts.jsonl", result.conflicts)

    committed, commit_msg = (False, "跳过提交")
    if commit:
        committed, commit_msg = git_commit(
            store_dir,
            f"chore(knowledge): 导入《{book}》术语 {len(entries)} 条"
            f"（+{result.added} ~{result.updated} 冲突{conflicts_written}）",
        )
    return {
        "store": str(store_dir),
        "book": book,
        "src_lang": src_lang,
        "tgt_lang": tgt_lang,
        "merged": len(entries),
        "added": result.added,
        "updated": result.updated,
        "conflicts": conflicts_written,
        "committed": committed,
        "commit_message": commit_msg,
    }


def knowledge_export(
    store_dir: Path,
    store: RunStore,
    *,
    src_lang: str | None = None,
    tgt_lang: str | None = None,
    include_pending: bool = False,
    force: bool = False,
) -> dict:
    """把统一库同语对条目导出为工作区 preprocessing/terms.csv（默认仅 confirmed）。"""
    src, tgt = _lang_pair(store, src_lang, tgt_lang)
    store_entries = load_store_csv(store_dir / "terminology.csv")
    entries = export_for_workspace(
        store_entries, src_lang=src, tgt_lang=tgt, include_pending=include_pending
    )
    target = store.preprocessing_dir / "terms.csv"
    if target.exists() and target.read_text(encoding="utf-8").strip() and not force:
        return {
            "store": str(store_dir),
            "src_lang": src,
            "tgt_lang": tgt,
            "target": str(target),
            "count": len(entries),
            "written": False,
            "reason": "preprocessing/terms.csv 已有内容；确认无冲突后加 --force 覆盖",
        }
    write_workspace_terms(target, entries)
    return {
        "store": str(store_dir),
        "src_lang": src,
        "tgt_lang": tgt,
        "target": str(target),
        "count": len(entries),
        "written": True,
        "reason": "",
    }


def knowledge_status(store_dir: Path) -> dict:
    """统一库统计 + git 状态（只读）。"""
    exists = store_dir.is_dir()
    entries = load_store_csv(store_dir / "terminology.csv") if exists else []
    conflicts = read_store_conflicts(store_dir / "conflicts.jsonl") if exists else []
    knowledge_dir = store_dir / "knowledge"
    knowledge_files = (
        sorted(p.name for p in knowledge_dir.glob("*.md")) if knowledge_dir.is_dir() else []
    )
    stats = store_stats(entries)
    stats["conflicts_ledger"] = len(conflicts)
    return {
        "store": str(store_dir),
        "exists": exists,
        "stats": stats,
        "knowledge_files": knowledge_files,
        "git": git_state(store_dir) if exists else {"repo": False},
    }


def knowledge_push(store_dir: Path, *, remote: str = "origin") -> dict:
    """推送 store 到远端（跨设备同步）。"""
    ok, message = git_push(store_dir, remote=remote)
    return {"store": str(store_dir), "remote": remote, "pushed": ok, "message": message}


__all__ = [
    "DEFAULT_STORE_DIRNAME",
    "git_available",
    "git_commit",
    "git_push",
    "git_state",
    "is_git_repo",
    "knowledge_export",
    "knowledge_import",
    "knowledge_import_file",
    "knowledge_init",
    "knowledge_push",
    "knowledge_status",
    "resolve_remote",
    "resolve_store_dir",
]
