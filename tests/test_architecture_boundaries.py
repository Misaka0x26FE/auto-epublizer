"""架构边界契约测试：固定依赖方向，防止反向导入。

三包依赖方向：``auto_common ← auto_translator ← auto_epublizer``。
- auto_common 是基础设施（config/llm/workspace），不依赖其余两包；
- auto_translator 是翻译引擎，只依赖 auto_common，不依赖 auto_epublizer；
- auto_epublizer 是转 EPUB + 编排层，可依赖 auto_common / auto_translator；
- orchestrator 不直接调用领域函数实现逻辑、不持有线程池；
- agents/ 是内部 LLM 调用服务，不得依赖编排、状态机或 RunStore。
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _module_imports(py_path: Path) -> set[str]:
    """把文件的所有导入解析为绝对模块名（含相对导入）。"""
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    rel_parts = py_path.relative_to(SRC).with_suffix("").parts
    pkg = rel_parts[0]
    package_parts = (pkg,) + rel_parts[1:-1]
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


def test_common_is_leaf() -> None:
    """auto_common 不得依赖 auto_translator / auto_epublizer。"""
    forbidden = {"auto_translator", "auto_epublizer"}
    for py in (SRC / "auto_common").rglob("*.py"):
        imports = _module_imports(py)
        bad = {m for m in imports if m.split(".")[0] in forbidden}
        assert not bad, f"{py.relative_to(SRC)} 不得依赖 {bad}"


def test_translator_does_not_import_epublizer() -> None:
    """auto_translator 只依赖 auto_common，不依赖 auto_epublizer。"""
    for py in (SRC / "auto_translator").rglob("*.py"):
        imports = _module_imports(py)
        bad = {m for m in imports if m.split(".")[0] == "auto_epublizer"}
        assert not bad, f"{py.relative_to(SRC)} 不得依赖 auto_epublizer"


def test_agents_do_not_depend_on_runstore_or_orchestration() -> None:
    """agents 是内部 LLM 调用服务，不得依赖编排、状态机或 RunStore。"""
    forbidden = {"auto_common.workspace", "auto_epublizer"}
    for py in (SRC / "auto_translator" / "agents").rglob("*.py"):
        imports = _module_imports(py)
        bad = {m for m in imports if m in forbidden or m.startswith("auto_epublizer")}
        assert not bad, f"{py.relative_to(SRC)} 不得依赖编排/状态机"


def test_domain_services_do_not_import_orchestrator() -> None:
    """EPUB 领域服务（ingest/structure/build/qa）不得导入 orchestrator。"""
    forbidden = {"auto_epublizer.orchestrator"}
    for sub in ("ingest", "structure", "build", "qa"):
        for py in (SRC / "auto_epublizer" / sub).rglob("*.py"):
            imports = _module_imports(py)
            assert not (imports & forbidden), f"{py.relative_to(SRC)} 不得导入 orchestrator"


def test_orchestrator_is_thin() -> None:
    """orchestrator 只装配路由，不持有线程池、不含核心领域实现体。"""
    orchestrator = SRC / "auto_epublizer" / "orchestrator.py"
    text = orchestrator.read_text(encoding="utf-8")
    assert "concurrent.futures" not in text
    assert "ThreadPoolExecutor" not in text
    assert "STATUS_" not in text
    assert "max_chars_per_batch" not in text
