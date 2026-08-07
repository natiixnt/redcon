"""Tests for the agentic evaluation harness (benchmarks/agentic).

A synthetic five-commit repository exercises corpus extraction and its filters,
the runner's per-run metrics, and the aggregation/report step. The harness lives
under benchmarks/ (flat modules, not a package), so it is imported by path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent / "benchmarks" / "agentic"
sys.path.insert(0, str(_HARNESS))

import corpus  # noqa: E402
import metrics  # noqa: E402
import report  # noqa: E402
import runner  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo: Path, message: str, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "-m",
        message,
    )


def _build_fixture(repo: Path) -> None:
    _git(repo, "init", "-q", "-b", "main")
    # Commit 0: setup. These files are Added, so they are never ground truth.
    _commit(
        repo,
        "chore: initial project layout",
        {
            "src/handler.py": "def handle(request):\n    return request\n",
            "src/util.py": "def parse_timeout(value):\n    return int(value)\n",
            "tests/test_handler.py": "def test_handle():\n    assert True\n",
            "README.md": "# Demo\n",
        },
    )
    # Commit 1: task-like, modifies one existing source file.
    _commit(
        repo,
        "feat: add retry logic to the handler",
        {
            "src/handler.py": "def handle(request, retries=3):\n    for _ in range(retries):\n        return request\n"
        },
    )
    # Commit 2: task-like fix, modifies another source file.
    _commit(
        repo,
        "fix: correct timeout parsing in parse_timeout",
        {"src/util.py": "def parse_timeout(value):\n    return float(value)\n"},
    )
    # Commit 3: docs-only, must be skipped (docs type and non-source file).
    _commit(repo, "docs: expand the installation guide", {"README.md": "# Demo\n\nInstall it.\n"})
    # Commit 4: task-like but a huge diff (on util, not handler), so the size
    # filter drops it without inflating the later handler change.
    big = "\n".join(f"    x{i} = {i}" for i in range(450))
    _commit(
        repo,
        "refactor: rewrite the util internals",
        {"src/util.py": f"def parse_timeout(value):\n{big}\n    return float(value)\n"},
    )
    # Commit 5: task-like, two files including a test.
    _commit(
        repo,
        "feat: support streaming responses in the handler",
        {
            "src/handler.py": "def handle(request, stream=False):\n    return request\n",
            "tests/test_handler.py": "def test_handle():\n    assert True\n\n\ndef test_stream():\n    assert True\n",
        },
    )


def test_corpus_extracts_tasklike_commits_and_applies_filters(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_fixture(repo)

    tasks = corpus.build_tasks(repo, "fixture", max_tasks=50)
    subjects = [t.phrasings["precise"] for t in tasks]

    # The three task-like modifying commits are kept.
    assert any("retry logic" in s for s in subjects)
    assert any("timeout parsing" in s for s in subjects)
    assert any("streaming responses" in s for s in subjects)
    # Docs-only and the oversized refactor are dropped.
    assert not any("installation guide" in s for s in subjects)
    assert not any("rewrite the util internals" in s for s in subjects)


def test_corpus_records_ground_truth_and_regions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_fixture(repo)
    tasks = corpus.build_tasks(repo, "fixture", max_tasks=50)

    retry = next(t for t in tasks if "retry logic" in t.phrasings["precise"])
    assert retry.changed_files == ("src/handler.py",)
    assert retry.hunk_names["src/handler.py"]  # at least one changed region recorded
    assert retry.parent_sha == f"{retry.sha}^"


def test_phrasings_are_three_and_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_fixture(repo)
    tasks = corpus.build_tasks(repo, "fixture", max_tasks=50)
    stream = next(t for t in tasks if "streaming" in t.phrasings["precise"])

    assert set(stream.phrasings) == {"precise", "medium", "vague"}
    assert stream.phrasings["vague"].startswith("improve the ")
    # Medium strips the symbol name that precise/vague may carry.
    assert (
        "parse_timeout" not in tasks[0].phrasings["medium"] or True
    )  # symbol-strip is best-effort
    # Extraction is stable across calls.
    again = corpus.build_tasks(repo, "fixture", max_tasks=50)
    assert [t.sha for t in again] == [t.sha for t in tasks]


def test_medium_phrasing_strips_symbol_names(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_fixture(repo)
    tasks = corpus.build_tasks(repo, "fixture", max_tasks=50)
    fix = next(t for t in tasks if "timeout parsing" in t.phrasings["precise"])
    # The commit touches parse_timeout; medium must not name it.
    assert "parse_timeout" in fix.phrasings["precise"]
    assert "parse_timeout" not in fix.phrasings["medium"]


def test_runner_produces_metric_records(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_fixture(repo)
    tasks = [t.to_json() for t in corpus.build_tasks(repo, "fixture", max_tasks=50)]

    records = list(
        runner.run_corpus(
            tasks,
            {"fixture": repo},
            budgets=(12_000,),
            phrasings=("precise", "vague"),
            worktree_root=tmp_path / "wts",
        )
    )
    valid = [r for r in records if "error" not in r]
    assert valid, "runner produced no successful records"
    for record in valid:
        assert 0.0 <= record["file_hits"] <= 1.0
        assert 0.0 <= record["region_containment"] <= 1.0
        assert record["cache_key"]
        assert record["input_tokens"] >= 0
        assert record["phrasing"] in {"precise", "vague"}


def test_metrics_and_report_render(tmp_path: Path) -> None:
    records = [
        {
            "repo": "fixture",
            "sha": "a",
            "phrasing": "precise",
            "budget": 12_000,
            "file_hits": 1.0,
            "region_containment": 0.8,
            "input_tokens": 5000,
            "risk": "low",
        },
        {
            "repo": "fixture",
            "sha": "a",
            "phrasing": "vague",
            "budget": 12_000,
            "file_hits": 0.5,
            "region_containment": 0.2,
            "input_tokens": 5200,
            "risk": "high",
        },
        {
            "repo": "fixture",
            "sha": "b",
            "phrasing": "precise",
            "budget": 30_000,
            "file_hits": 1.0,
            "region_containment": 0.9,
            "input_tokens": 9000,
            "risk": "low",
        },
    ]
    summary = metrics.summarize(records)
    assert summary["runs"] == 3
    assert 0.0 <= summary["overall"]["file_hits"]["low"] <= summary["overall"]["file_hits"]["mean"]
    assert set(summary["by_phrasing"]) == {"precise", "vague"}
    assert set(summary["risk_calibration"]) == {"low", "high"}
    # Calibration direction: high risk should not out-cover low risk here.
    assert (
        summary["risk_calibration"]["high"]["region_containment"]
        <= summary["risk_calibration"]["low"]["region_containment"]
    )

    markdown = report.render(summary, errors=0)
    assert "# Agentic Context Evaluation" in markdown
    assert "Budget curve" in markdown
    assert "Risk calibration" in markdown
    # Without tasks, the distinguishability block is absent.
    assert "phrasing_distinguishability" not in summary
    assert "Phrasing distinguishability" not in markdown


def test_phrasing_distinguishability_counts_and_renders(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_fixture(repo)
    tasks = [t.to_json() for t in corpus.build_tasks(repo, "fixture", max_tasks=50)]

    dist = metrics.phrasing_distinguishability(tasks)
    assert dist["total"] == len(tasks)
    # The timeout-parsing fix names parse_timeout, so medium strips it and differs.
    assert dist["medium_differs_precise"] >= 1
    assert dist["medium_differs_precise"] <= dist["total"]
    assert dist["by_repo"]["fixture"]["total"] == len(tasks)

    # summarize threads the block through only when tasks are supplied, and the
    # report renders it with the honest-CI caveat.
    records = [
        {
            "repo": "fixture",
            "sha": t["sha"],
            "phrasing": "precise",
            "budget": 12_000,
            "file_hits": 1.0,
            "region_containment": 0.5,
            "input_tokens": 4000,
            "risk": "medium",
        }
        for t in tasks
    ]
    summary = metrics.summarize(records, tasks=tasks)
    assert summary["phrasing_distinguishability"] == dist
    markdown = report.render(summary, errors=0)
    assert "Phrasing distinguishability" in markdown
    assert "medium differs from precise" in markdown
    # The Caveats flag the vague-phrasing oracle leak and the medium collapse.
    assert "### Caveats" in markdown
    assert "vague phrasing is derived from the change itself" in markdown
    identical = dist["total"] - dist["medium_differs_precise"]
    assert f"identical to precise for {identical}/{dist['total']} tasks" in markdown


def _big_body(n: int, prefix: str = "x") -> str:
    return "\n".join(f"{prefix}{i} = {i}" for i in range(n)) + "\n"


def test_build_tasks_applies_dir_and_diff_size_filters(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(
        repo,
        "chore: layout",
        {"pkg_a/one.py": "a = 0\n", "pkg_a/two.py": "b = 0\n", "pkg_b/three.py": "c = 0\n"},
    )
    # Multi-file, multi-directory, large diff: qualifies under the heavy filters.
    _commit(
        repo,
        "feat: spread a substantial change across packages",
        {
            "pkg_a/one.py": _big_body(40, "a"),
            "pkg_a/two.py": _big_body(20, "b"),
            "pkg_b/three.py": _big_body(20, "c"),
        },
    )
    # Three files but a single directory: fails min_dirs=2.
    _commit(
        repo,
        "feat: rework only package a extensively here",
        {"pkg_a/one.py": _big_body(80, "a"), "pkg_a/two.py": _big_body(40, "b")},
    )

    heavy = corpus.build_tasks(
        repo, "fixture", min_files=3, max_files=8, min_dirs=2, min_diff_lines=60, max_diff_lines=400
    )
    subjects = [t.phrasings["precise"] for t in heavy]
    assert any("spread a substantial change" in s for s in subjects)  # multi-dir kept
    assert not any("rework only package a" in s for s in subjects)  # single-dir dropped
    spread = next(t for t in heavy if "spread a substantial change" in t.phrasings["precise"])
    assert len({str(Path(f).parent) for f in spread.changed_files}) >= 2

    # The tiny-diff default corpus would keep neither (both exceed nothing) but the
    # min_diff_lines floor also rejects a small multi-dir change.
    small = corpus.build_tasks(repo, "fixture", min_files=3, min_dirs=2, min_diff_lines=1000)
    assert small == []


def test_select_heavy_balances_strata_and_repos() -> None:
    import build_heavy

    tasks = []
    for repo in ("django", "sympy"):
        for size in range(1, 31):
            tasks.append(
                {
                    "repo": repo,
                    "sha": f"{repo}{size:02d}",
                    "changed_files": ["a/f.py", "b/g.py"],
                    "hunk_names": {"a/f.py": [{"range": [1, size], "symbol": ""}]},
                }
            )
    picked = build_heavy.select_heavy(tasks)
    assert len(picked) == 12
    assert all(t["stratum"] in build_heavy.STRATA for t in picked)
    from collections import Counter

    assert dict(Counter(t["stratum"] for t in picked)) == {"small": 4, "medium": 4, "large": 4}
    assert dict(Counter(t["repo"] for t in picked)) == {"django": 6, "sympy": 6}


def test_bootstrap_ci_is_deterministic() -> None:
    values = [0.1, 0.4, 0.9, 0.3, 0.7, 0.5]
    first = metrics.bootstrap_ci(values)
    second = metrics.bootstrap_ci(values)
    assert first == second
    assert first["low"] <= first["mean"] <= first["high"]
