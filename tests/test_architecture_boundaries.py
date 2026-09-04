"""架构边界契约测试：固定依赖方向，防止反向导入。

三包依赖方向：``auto_common ← auto_translator ← auto_epublizer``。
- auto_common 是基础设施（config/workspace），不依赖其余两包，且不含任何 LLM 模块
  （唯一 LLM 原则）；
- auto_translator 是术语/对齐/G0 校验等确定性领域逻辑，只依赖 auto_common，
  不依赖 auto_epublizer，也不做任何 LLM 调用；
- auto_epublizer 是转 EPUB + 编排层，可依赖 auto_common / auto_translator；
- orchestrator 不直接调用领域函数实现逻辑、不持有线程池。
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


def test_common_has_no_llm_module() -> None:
    """唯一 LLM 原则：auto_common 不含任何 llm 模块或文件。"""
    assert not (SRC / "auto_common" / "llm").exists(), "auto_common/llm 应已移除"
    for py in (SRC / "auto_common").rglob("*.py"):
        assert "llm" not in py.parts, f"{py.relative_to(SRC)} 属 LLM 模块"


def test_no_llm_api_calls_anywhere() -> None:
    """唯一 LLM 原则：全库不得出现 LLM 客户端/补全调用符号。"""
    forbidden_symbols = (
        "LLMClient",
        "complete_json",
        "chat/completions",
        "OpenAICompatible",
        "create_client",
        "FakeClient",
    )
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for sym in forbidden_symbols:
            assert sym not in text, f"{py.relative_to(SRC)} 含 LLM 调用符号 {sym}"


def test_translator_does_not_import_epublizer() -> None:
    """auto_translator 只依赖 auto_common，不依赖 auto_epublizer。"""
    for py in (SRC / "auto_translator").rglob("*.py"):
        imports = _module_imports(py)
        bad = {m for m in imports if m.split(".")[0] == "auto_epublizer"}
        assert not bad, f"{py.relative_to(SRC)} 不得依赖 auto_epublizer"


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
