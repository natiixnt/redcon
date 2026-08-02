"""Changed-file targeting.

Files named as changed (via --changed) and their one-hop import-graph
neighbours get a deterministic boost, so a task scoped to a diff surfaces the
files it touches even when keyword overlap is weak.
"""

from __future__ import annotations

from pathlib import Path

from redcon.config import ScoreSettings
from redcon.scanners.repository import scan_repository
from redcon.scorers.relevance import score_files


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed(repo: Path) -> None:
    # service_a imports service_b, so service_b is a one-hop neighbour.
    _write(
        repo / "pkg" / "service_a.py",
        "from pkg.service_b import helper\n\n\ndef run():\n    return helper()\n",
    )
    _write(repo / "pkg" / "service_b.py", "def helper():\n    return 1\n")
    _write(repo / "pkg" / "service_c.py", "def unrelated():\n    return 2\n")


def test_changed_file_and_neighbour_are_boosted(tmp_path: Path) -> None:
    _seed(tmp_path)
    records = scan_repository(tmp_path)
    # A task with no keyword overlap: the changed boost is the dominant signal.
    ranked = score_files(
        "refactor the widget subsystem", records, changed_paths={"pkg/service_a.py"}
    )
    by_path = {r.file.path: r for r in ranked}

    assert {"pkg/service_a.py", "pkg/service_b.py", "pkg/service_c.py"} <= set(by_path)
    a = by_path["pkg/service_a.py"]
    b = by_path["pkg/service_b.py"]
    c = by_path["pkg/service_c.py"]

    # The explicit file and its import neighbour both outrank the untargeted file.
    assert a.score > b.score > c.score
    assert a.score_breakdown.get("changed_file", 0.0) > 0
    assert b.score_breakdown.get("changed_neighbor", 0.0) > 0
    assert "changed_file" not in c.score_breakdown
    assert "changed_neighbor" not in c.score_breakdown
    assert any("explicitly changed file" in r for r in a.reasons)
    assert any("changed file" in r for r in b.reasons)


def test_changed_targeting_is_deterministic(tmp_path: Path) -> None:
    _seed(tmp_path)
    records = scan_repository(tmp_path)
    first = score_files("do the thing", records, changed_paths={"pkg/service_a.py"})
    second = score_files("do the thing", records, changed_paths={"pkg/service_a.py"})
    assert [(r.file.path, r.score) for r in first] == [(r.file.path, r.score) for r in second]


def test_changed_paths_can_use_relative_or_none(tmp_path: Path) -> None:
    _seed(tmp_path)
    records = scan_repository(tmp_path)
    # No changed set: nothing gets a changed-file boost.
    base = {r.file.path: r for r in score_files("refactor the widget subsystem", records)}
    assert all(r.score_breakdown.get("changed_file", 0.0) == 0.0 for r in base.values())
    # An unknown path is ignored rather than raising.
    ranked = score_files(
        "refactor the widget subsystem", records, changed_paths={"does/not/exist.py"}
    )
    assert all(r.score_breakdown.get("changed_file", 0.0) == 0.0 for r in ranked)


def test_changed_boost_disabled_by_zero_config(tmp_path: Path) -> None:
    _seed(tmp_path)
    records = scan_repository(tmp_path)
    settings = ScoreSettings(changed_file_boost=0.0, changed_neighbor_boost=0.0)
    ranked = score_files(
        "refactor the widget subsystem",
        records,
        settings=settings,
        changed_paths={"pkg/service_a.py"},
    )
    assert all(r.score_breakdown.get("changed_file", 0.0) == 0.0 for r in ranked)
