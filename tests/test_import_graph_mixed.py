"""Import-graph coverage for mixed Python/TypeScript repositories.

A single repo often holds a Python backend and a TypeScript frontend. The
import graph must propagate relevance within each language (a relevant file
boosts its importers and importees) without ever linking across languages,
since there is no resolver that bridges a Python import to a TS module. These
tests build a mixed fixture and check both properties.
"""

from __future__ import annotations

from pathlib import Path

from redcon.scanners.repository import scan_repository
from redcon.scorers import import_graph
from redcon.scorers.import_graph import build_import_graph
from redcon.scorers.relevance import score_files

_TS_FAMILY = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_mixed_repo(repo: Path) -> None:
    # Python backend: app (entrypoint) -> auth -> token_store.
    _write(repo / "services" / "app.py", "from .auth import authenticate\n\nauthenticate('x')\n")
    _write(
        repo / "services" / "auth.py",
        "from .token_store import verify_token\n\n\n"
        "def authenticate(token: str) -> bool:\n    return verify_token(token)\n",
    )
    _write(
        repo / "services" / "token_store.py",
        "def verify_token(token: str) -> bool:\n    return token.startswith('prod_')\n",
    )
    # TypeScript frontend: dashboard -> widget -> format.
    _write(
        repo / "web" / "dashboard.tsx",
        "import { renderWidget } from './widget';\n\nrenderWidget();\n",
    )
    _write(
        repo / "web" / "widget.ts",
        "import { formatValue } from './format';\n\n"
        "export function renderWidget(): string {\n  return formatValue(1);\n}\n",
    )
    _write(
        repo / "web" / "format.ts",
        "export function formatValue(n: number): string {\n  return String(n);\n}\n",
    )


def _import_graph_signal(item) -> float:
    return item.score_breakdown.get("import_graph", 0.0)


def test_python_relevance_propagates_without_touching_typescript(tmp_path: Path) -> None:
    import_graph._GRAPH_CACHE.clear()
    _seed_mixed_repo(tmp_path)
    records = scan_repository(tmp_path)
    ranked = score_files("refactor auth login token flow", records)
    by_path = {item.file.path: item for item in ranked}

    # The Python chain propagates: token_store is imported by the relevant auth
    # file, and app depends on it.
    token_store = by_path["services/token_store.py"]
    assert _import_graph_signal(token_store) > 0
    assert any("imported by relevant file" in r for r in token_store.reasons)
    assert any("depends on relevant module" in r for r in by_path["services/app.py"].reasons)

    # No seed-driven propagation crosses into the TypeScript files. (Structural
    # entrypoint-adjacency is task-independent and stays within a language, so
    # it is not what we guard against here.)
    for ts_path in ("web/dashboard.tsx", "web/widget.ts", "web/format.ts"):
        reasons = by_path[ts_path].reasons
        assert not any("imported by relevant file" in r for r in reasons)
        assert not any("depends on relevant module" in r for r in reasons)


def test_typescript_relevance_propagates_without_touching_python(tmp_path: Path) -> None:
    import_graph._GRAPH_CACHE.clear()
    _seed_mixed_repo(tmp_path)
    records = scan_repository(tmp_path)
    ranked = score_files("update dashboard widget formatting", records)
    by_path = {item.file.path: item for item in ranked}

    # The TypeScript chain propagates: format is imported by the relevant widget,
    # and dashboard depends on it.
    fmt = by_path["web/format.ts"]
    assert _import_graph_signal(fmt) > 0
    assert any("imported by relevant file" in r for r in fmt.reasons)
    assert any("depends on relevant module" in r for r in by_path["web/dashboard.tsx"].reasons)

    # No seed-driven propagation crosses into the Python files.
    for py_path in ("services/app.py", "services/auth.py", "services/token_store.py"):
        reasons = by_path[py_path].reasons
        assert not any("imported by relevant file" in r for r in reasons)
        assert not any("depends on relevant module" in r for r in reasons)


def test_import_edges_never_cross_languages(tmp_path: Path) -> None:
    import_graph._GRAPH_CACHE.clear()
    _seed_mixed_repo(tmp_path)
    # Same basename in both languages, each importing its own sibling. The
    # resolver must not bridge the two.
    _write(tmp_path / "services" / "gateway.py", "from .shared import helper\n\nhelper()\n")
    _write(tmp_path / "services" / "shared.py", "def helper() -> int:\n    return 1\n")
    _write(tmp_path / "web" / "panel.ts", "import { helper } from './shared';\n\nhelper();\n")
    _write(tmp_path / "web" / "shared.ts", "export function helper(): number {\n  return 1;\n}\n")

    records = scan_repository(tmp_path)
    graph = build_import_graph(records)

    def family(path: str) -> str:
        return "ts" if any(path.endswith(ext) for ext in _TS_FAMILY) else "py"

    # No edge in either direction connects a Python file to a TypeScript file.
    for source, targets in graph.outgoing.items():
        for target in targets:
            assert family(source) == family(target), f"cross-language edge {source} -> {target}"

    # Same-basename imports resolve within their own language.
    assert "services/shared.py" in graph.outgoing.get("services/gateway.py", set())
    assert "web/shared.ts" not in graph.outgoing.get("services/gateway.py", set())
    assert "web/shared.ts" in graph.outgoing.get("web/panel.ts", set())
    assert "services/shared.py" not in graph.outgoing.get("web/panel.ts", set())
