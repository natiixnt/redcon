"""Tests for the task-independent repository brief (`redcon brief`).

The brief is a deterministic map of a repository's shape built from scan, role,
and import-graph aggregates, with no task input and no per-change file ranking.
These pin the guarantees the feature depends on: determinism (same tree, same
brief), the token ceiling, task independence, and that the expected sections and
geography are present.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from redcon.brief import build_brief


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "myproject"
    repo.mkdir()
    _git(repo, "init", "-q")
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init")
    return repo


_FILES = {
    "myproject/__init__.py": "",
    "myproject/__main__.py": "def main():\n    return 0\n",
    "myproject/cli.py": "import myproject.core.engine\n",
    "myproject/core/__init__.py": "",
    "myproject/core/engine.py": "def run():\n    return 1\n",
    "myproject/core/planner.py": "import myproject.core.engine\n\n\ndef plan():\n    return 2\n",
    "myproject/db/__init__.py": "",
    "myproject/db/models.py": "class Model:\n    pass\n",
    "myproject/db/backends/sqlite.py": "def connect():\n    return None\n",
    # A main.py deep in the tree is not a process entry point (depth guard drops it).
    "myproject/views/admin/main.py": "def changelist():\n    return None\n",
    "tests/test_engine.py": "def test_run():\n    assert True\n",
    "tests/test_models.py": "def test_model():\n    assert True\n",
    "tests/conftest.py": "import pytest\n",
    "docs/guide.md": "# Guide\n",
    "pyproject.toml": "[project]\nname = 'myproject'\n",
    "Makefile": "test:\n\tpytest\n",
}
# Extra subpackages so the geography section is long enough to test trimming.
_FILES.update({f"myproject/mod{i:02d}/impl.py": "def f():\n    return 1\n" for i in range(15)})


def test_brief_is_deterministic(tmp_path: Path):
    repo = _repo(tmp_path, _FILES)
    first = build_brief(repo).text
    second = build_brief(repo).text
    assert first == second


def test_brief_has_expected_sections(tmp_path: Path):
    repo = _repo(tmp_path, _FILES)
    text = build_brief(repo).text
    assert "# Repository brief: myproject" in text
    assert "## Module geography" in text
    assert "## Central modules" in text
    assert "## Entry points" in text
    assert "## Test layout" in text
    assert "## Build and config" in text


def test_brief_maps_geography_and_entry_points(tmp_path: Path):
    repo = _repo(tmp_path, _FILES)
    brief = build_brief(repo)
    text = brief.text
    # Subpackages of the dominant package appear as geography, not a ranked list.
    assert "`myproject/core/`" in text
    assert "`myproject/db/`" in text
    # The db descriptor mentions its subdirectory (backends/) and module (models).
    assert "backends/" in text
    # Entry points are the conventional production mains.
    assert "myproject/__main__.py" in text
    # Build and config surfaces the root files that exist.
    assert "`pyproject.toml`" in text
    assert "`Makefile`" in text


def test_brief_central_modules_use_import_degree(tmp_path: Path):
    # engine is imported by cli and planner, so it is the most central module.
    repo = _repo(tmp_path, _FILES)
    text = build_brief(repo).text
    section = text.split("## Central modules", 1)[1].split("##", 1)[0]
    assert "`myproject/core/engine.py` (imported by 2 modules)" in section


def test_brief_entrypoint_depth_guard(tmp_path: Path):
    # A main.py deep in the tree is not surfaced as an entry point.
    repo = _repo(tmp_path, _FILES)
    entry = build_brief(repo).text.split("## Entry points", 1)[1].split("##", 1)[0]
    assert "myproject/__main__.py" in entry
    assert "views/admin/main.py" not in entry


def test_brief_test_layout_counts_conftest(tmp_path: Path):
    repo = _repo(tmp_path, _FILES)
    layout = build_brief(repo).text.split("## Test layout", 1)[1].split("##", 1)[0]
    assert "1 file named `conftest.py`" in layout


def test_brief_respects_token_cap(tmp_path: Path):
    # A ceiling below the full brief forces geography to be trimmed to fit and
    # marked truncated. The cap sits above the fixed-section floor so it is
    # reachable by trimming geography alone.
    repo = _repo(tmp_path, _FILES)
    full = build_brief(repo, max_tokens=10000)
    cap = 250
    assert cap < full.tokens, "fixture is too small to exercise trimming"
    brief = build_brief(repo, max_tokens=cap)
    assert brief.tokens <= cap
    assert brief.truncated


def test_brief_names_no_task_or_ground_truth(tmp_path: Path):
    # Task independence: the brief carries geography only. It must not contain a
    # per-file ranking header or any task string (there is no task input at all).
    repo = _repo(tmp_path, _FILES)
    text = build_brief(repo).text.lower()
    assert "task" not in text.replace("task-independent", "").replace("no per-change file list", "")
    assert "score" not in text
    assert "rank" not in text
