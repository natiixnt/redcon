"""Tests for the one-shot experiment harness (benchmarks/agentic/oneshot_arm.py).

Cover the pure logic - keyword ranking, unified-diff parsing, and the diff-overlap
metric - without spawning the CLI, so they are deterministic and free.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent / "benchmarks" / "agentic"
sys.path.insert(0, str(_HARNESS))

import oneshot_arm  # noqa: E402


def test_keywords_drop_stopwords_and_short_tokens():
    kws = oneshot_arm._keywords("Add retry logic to the HTTP client")
    assert "retry" in kws and "logic" in kws and "http" in kws and "client" in kws
    assert "add" not in kws and "the" not in kws and "to" not in kws


def test_parse_unified_diff_extracts_files_and_lines():
    patch = (
        "--- a/pkg/auth.py\n"
        "+++ b/pkg/auth.py\n"
        "@@ -10,2 +10,3 @@\n"
        "-old\n"
        "+new\n"
        "--- a/pkg/db.py\n"
        "+++ b/pkg/db.py\n"
        "@@ -5 +5 @@\n"
    )
    parsed = oneshot_arm.parse_unified_diff(patch)
    assert parsed["pkg/auth.py"] == {10, 11}
    assert parsed["pkg/db.py"] == {5}
    # Non-diff text parses to nothing.
    assert oneshot_arm.parse_unified_diff("Sorry, I cannot do that.") == {}


def test_diff_overlap_scores_file_and_line_levels():
    task = {
        "changed_files": ["pkg/auth.py"],
        "hunk_names": {"pkg/auth.py": [{"range": [10, 11], "symbol": ""}]},
    }
    good = "--- a/pkg/auth.py\n+++ b/pkg/auth.py\n@@ -10,2 +10,2 @@\n-x\n+y\n"
    ov = oneshot_arm.diff_overlap(good, task)
    assert ov["parsed"] is True
    assert ov["file_overlap"] == 1.0
    assert ov["line_overlap"] == 1.0
    # Wrong file: no overlap.
    wrong = "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-a\n+b\n"
    ov2 = oneshot_arm.diff_overlap(wrong, task)
    assert ov2["file_overlap"] == 0.0 and ov2["line_overlap"] == 0.0
    # Parse failure scores 0 and flags parsed=False.
    ov3 = oneshot_arm.diff_overlap("not a diff", task)
    assert ov3["parsed"] is False and ov3["file_overlap"] == 0.0


def test_naive_context_ranks_by_keyword_and_fits_budget(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    (repo / "auth.py").write_text("def login(user, password):\n    return retry(login)\n")
    (repo / "unrelated.py").write_text("def helper():\n    return 1\n")
    git("add", "-A")
    git("-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init")
    task = {"phrasings": {"precise": "add retry to login"}}
    context, files = oneshot_arm.naive_context(repo, task, budget=30_000)
    assert "auth.py" in files  # the keyword-matching file is selected
    assert files[0] == "auth.py"  # and ranked first
    assert "auth.py" in context


def test_is_valid_gates_resume_on_real_completed_runs():
    # A real completed run counts as done.
    assert oneshot_arm._is_valid({"cost_usd": 1.5, "is_error": False}) is True
    # Session-limit, error, and zero-cost rows never count as done (they get re-run).
    assert oneshot_arm._is_valid({"cost_usd": 0, "is_error": True, "session_limited": True}) is False
    assert oneshot_arm._is_valid({"error": "timeout"}) is False
    assert oneshot_arm._is_valid({"cost_usd": 0, "is_error": False}) is False
    assert oneshot_arm._is_valid({"cost_usd": None}) is False
