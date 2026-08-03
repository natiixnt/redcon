"""File-role persistence.

A file's role (prod/test/docs/example/config/generated) is classified once at
scan time, cached on FileRecord in the scan index, and carried onto RankedFile
so it appears in run.json and plan output without being recomputed per run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import redcon.scorers.file_roles as file_roles
from redcon.core import pipeline
from redcon.core.render import render_plan_markdown
from redcon.scanners.incremental import load_scan_index, refresh_scan_index
from redcon.schemas.models import SCAN_INDEX_FILE, FileRecord
from redcon.stages.workflow import as_json_dict


def _record(path: str, role: str = "") -> FileRecord:
    return FileRecord(
        path=path,
        absolute_path=f"/x/{path}",
        extension=".py",
        size_bytes=1,
        line_count=1,
        content_hash="h",
        content_preview="",
        role=role,
    )


def _seed(repo: Path) -> None:
    (repo / "auth").mkdir(parents=True, exist_ok=True)
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "auth" / "login.py").write_text("def login(t):\n    return bool(t)\n")
    (repo / "tests" / "test_login.py").write_text("def test_login():\n    assert True\n")


def test_file_record_classifies_role_on_construction() -> None:
    assert _record("auth/login.py").role == "prod"
    assert _record("tests/test_login.py").role == "test"


def test_explicit_cached_role_is_not_overwritten() -> None:
    # A role loaded from the index is preserved rather than reclassified.
    assert _record("tests/test_login.py", role="config").role == "config"


def test_run_plan_serializes_role(tmp_path: Path) -> None:
    _seed(tmp_path)
    data = pipeline.run_plan("fix login auth", tmp_path)
    by_path = {r["path"]: r for r in data["ranked_files"]}
    assert by_path["auth/login.py"]["role"] == "prod"
    assert by_path["tests/test_login.py"]["role"] == "test"


def test_run_pack_serializes_role(tmp_path: Path) -> None:
    _seed(tmp_path)
    data = as_json_dict(pipeline.run_pack("fix login auth", tmp_path, max_tokens=5000))
    assert data["ranked_files"]
    assert all("role" in rf for rf in data["ranked_files"])


def test_plan_markdown_shows_role_tag(tmp_path: Path) -> None:
    _seed(tmp_path)
    md = render_plan_markdown(pipeline.run_plan("fix login auth", tmp_path))
    assert "[test]" in md
    assert "[prod]" in md


def test_scan_index_caches_role_json(tmp_path: Path) -> None:
    _seed(tmp_path)
    refresh_scan_index(tmp_path, use_sqlite=False)
    index = load_scan_index(tmp_path / SCAN_INDEX_FILE)
    roles = {e["record"]["path"]: e["record"]["role"] for e in index["entries"]}
    assert roles["tests/test_login.py"] == "test"
    assert roles["auth/login.py"] == "prod"


def test_cached_role_is_not_recomputed_on_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    refresh_scan_index(tmp_path)  # first scan populates and persists role

    def boom(path: str) -> str:
        raise AssertionError(f"role recomputed for {path}")

    monkeypatch.setattr(file_roles, "classify_file_role", boom)
    # Unchanged tree: records load from the cache with role already present, so
    # the classifier must not be called again.
    result = refresh_scan_index(tmp_path)
    roles = {r.path: r.role for r in result.records}
    assert roles["tests/test_login.py"] == "test"
    assert roles["auth/login.py"] == "prod"
