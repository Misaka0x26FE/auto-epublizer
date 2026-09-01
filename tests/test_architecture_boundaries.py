"""架构边界契约测试：固定依赖方向，防止反向导入。

依赖方向：CLI → Orchestrator（薄 façade）→ 领域服务 → agents / llm / glossary / workspace。
- orchestrator 不直接调用领域函数实现逻辑、不持有线程池；
- 下层不得反向导入 orchestrator；
- agents/ 是内部 LLM 调用服务，不得依赖编排、状态机或 RunStore。
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "auto_epublizer"


def _module_imports(py_path: Path) -> set[str]:
    """把文件的所有导入解析为绝对模块名（含相对导入）。"""
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    rel_parts = py_path.relative_to(SRC).with_suffix("").parts
    package_parts = ("auto_epublizer",) + rel_parts[:-1]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            level = node.level
            if level == 0:
                imports.add(node.module)
            else:
                base = package_parts[: len(package_parts) - level + 1]
                imports.add(".".join(base + tuple(node.module.split("."))))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
    return imports


def test_domain_services_do_not_import_orchestrator() -> None:
    forbidden = {"auto_epublizer.orchestrator"}
    for sub in (
        "ingest",
        "structure",
        "analysis",
        "translation",
        "review",
        "build",
        "qa",
        "glossary",
        "llm",
        "workspace",
        "genre",
    ):
        for py in (SRC / sub).rglob("*.py"):
            imports = _module_imports(py)
            assert not (imports & forbidden), f"{py.relative_to(SRC)} 不得导入 orchestrator"


def test_agents_do_not_depend_on_orchestration_state_or_runstore() -> None:
    forbidden = {"auto_epublizer.orchestrator", "auto_epublizer.workspace"}
    agents_dir = SRC / "agents"
    if not agents_dir.exists():
        return
    for py in agents_dir.rglob("*.py"):
        imports = _module_imports(py)
        assert not (imports & forbidden), f"{py.relative_to(SRC)} 不得依赖编排/状态机"


def test_workspace_and_llm_do_not_import_domain_services() -> None:
    forbidden = {"ingest", "structure", "analysis", "translation", "review", "build", "qa"}
    for sub in ("workspace", "llm"):
        for py in (SRC / sub).rglob("*.py"):
            imports = _module_imports(py)
            bad = {
                m
                for m in imports
                if m.startswith("auto_epublizer.") and m.split(".")[1] in forbidden
            }
            assert not bad, f"{py.relative_to(SRC)} 不得导入领域服务"


def test_orchestrator_does_not_hold_thread_pool() -> None:
    orchestrator = SRC / "orchestrator.py"
    assert "concurrent.futures" not in orchestrator.read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" not in orchestrator.read_text(encoding="utf-8")


def test_orchestrator_is_thin() -> None:
    """orchestrator 只装配路由，不包含核心领域实现（无状态机/切片/渲染逻辑体）。"""
    orchestrator = SRC / "orchestrator.py"
    text = orchestrator.read_text(encoding="utf-8")
    assert "STATUS_" not in text
    assert "max_chars_per_batch" not in text
