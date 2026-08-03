"""Scoring breakdown.

Each ranked file exposes a ``score_breakdown``: the weighted contribution of
every ranking signal (path/content keywords, symbols, import-graph, role and
changed-file boosts), in ``plan`` output, ``run.json``, and the human plan view.
Deterministic.
"""

from __future__ import annotations

from pathlib import Path

from redcon.core import pipeline
from redcon.core.render import render_plan_markdown
from redcon.schemas.models import FileRecord, RankedFile
from redcon.stages.workflow import _serialize_ranked_file


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_serialize_includes_sorted_score_breakdown() -> None:
    rf = RankedFile(
        file=FileRecord(
            path="a.py",
            absolute_path="/x/a.py",
            extension=".py",
            size_bytes=1,
            line_count=1,
            content_hash="h",
            content_preview="",
        ),
        score=3.0,
        heuristic_score=3.0,
        score_breakdown={"path_keyword": 2.0, "content_keyword": 1.0, "import_graph": 0.9},
    )
    data = _serialize_ranked_file(rf)
    assert "score_breakdown" in data
    # Keys are emitted in sorted order for deterministic output.
    assert list(data["score_breakdown"]) == sorted(data["score_breakdown"])
    assert data["score_breakdown"]["path_keyword"] == 2.0


def _seed(repo: Path) -> None:
    _write(repo / "auth" / "login.py", "def login(token):\n    return validate(token)\n")
    _write(repo / "auth" / "validate.py", "def validate(token):\n    return bool(token)\n")


def test_plan_output_exposes_breakdown(tmp_path: Path) -> None:
    _seed(tmp_path)
    data = pipeline.run_plan("fix the login auth flow", tmp_path)
    ranked = data.get("ranked_files") or []
    assert ranked
    top = ranked[0]
    assert isinstance(top.get("score_breakdown"), dict)
    assert top["score_breakdown"]  # a keyword-matching file has at least one signal


def test_breakdown_is_deterministic(tmp_path: Path) -> None:
    _seed(tmp_path)
    a = pipeline.run_plan("fix the login auth flow", tmp_path)
    b = pipeline.run_plan("fix the login auth flow", tmp_path)
    assert [r["score_breakdown"] for r in a["ranked_files"]] == [
        r["score_breakdown"] for r in b["ranked_files"]
    ]


def test_human_plan_shows_signals_line(tmp_path: Path) -> None:
    _seed(tmp_path)
    data = pipeline.run_plan("fix the login auth flow", tmp_path)
    md = render_plan_markdown(data)
    assert "signals:" in md
    # A concrete signal from the top file appears in the rendered breakdown.
    top_signals = data["ranked_files"][0]["score_breakdown"]
    some_key = sorted(top_signals)[0]
    assert some_key in md
