"""Self-contained HTML reports for run, diff and benchmark artifacts.

The `--html` flag adds an HTML report alongside the JSON/Markdown outputs. The
HTML must be a single self-contained document (inline CSS, no external
requests) and must carry the key sections, including score_breakdown, role and
prompt_cache_key for runs and baseline_comparison for benchmarks.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from redcon.core.html_report import render_benchmark_html, render_diff_html, render_run_html


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()

    def handle_starttag(self, tag: str, attrs: object) -> None:
        self.tags.add(tag)


def _parse_tags(html: str) -> set[str]:
    parser = _TagCollector()
    parser.feed(html)  # raises if the markup is not parseable
    return parser.tags


def _assert_self_contained(html: str) -> None:
    lowered = html.lower()
    assert html.lstrip().startswith("<!doctype html>")
    assert "<style>" in lowered
    for external in ("http://", "https://", "<link", "src=", "<script"):
        assert external not in lowered, f"HTML is not self-contained: found {external!r}"


def _run_data() -> dict:
    return {
        "command": "pack",
        "task": "harden auth",
        "repo": "/tmp/example",
        "max_tokens": 5000,
        "prompt_cache_key": "abcd1234ef567890",
        "budget": {"estimated_input_tokens": 120, "estimated_saved_tokens": 900},
        "files_included": ["auth/login.py"],
        "files_skipped": ["auth/legacy.py"],
        "ranked_files": [
            {
                "path": "auth/login.py",
                "score": 4.2,
                "role": "prod",
                "score_breakdown": {"path_keyword": 2.0, "import_graph": 0.9},
            }
        ],
    }


def test_run_html_is_self_contained_and_parses() -> None:
    html = render_run_html(_run_data())
    _assert_self_contained(html)
    tags = _parse_tags(html)
    assert {"html", "head", "body", "table", "h1"} <= tags


def test_run_html_carries_required_sections() -> None:
    html = render_run_html(_run_data())
    assert "Redcon Pack Report" in html
    assert "abcd1234ef567890" in html  # prompt_cache_key
    assert "auth/login.py" in html
    assert "prod" in html  # role tag
    assert "path_keyword" in html and "import_graph" in html  # score_breakdown signals


def test_run_html_escapes_content() -> None:
    data = _run_data()
    data["task"] = "fix <script>alert(1)</script> & co"
    html = render_run_html(data)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_diff_html_renders_sections() -> None:
    data = {
        "command": "diff",
        "old_run": "old.json",
        "new_run": "new.json",
        "task_diff": {"old_task": "a", "new_task": "b", "changed": True},
        "context_diff": {
            "files_added": ["x.py"],
            "files_removed": ["y.py"],
            "added_count": 1,
            "removed_count": 1,
        },
        "ranked_score_changes": [
            {
                "path": "x.py",
                "old_score": None,
                "new_score": 3.0,
                "delta": 3.0,
                "change_type": "added",
            }
        ],
        "budget_delta": {},
    }
    html = render_diff_html(data)
    _assert_self_contained(html)
    assert {"table", "body"} <= _parse_tags(html)
    assert "Redcon Diff Report" in html
    assert "x.py" in html and "added" in html


def test_benchmark_html_includes_baseline_comparison() -> None:
    data = {
        "command": "benchmark",
        "task": "demo",
        "repo": "/tmp/example",
        "max_tokens": 5000,
        "baseline_full_context_tokens": 1000,
        "strategies": [
            {
                "strategy": "compressed_pack",
                "estimated_input_tokens": 300,
                "estimated_saved_tokens": 700,
                "files_included": ["a.py"],
                "quality_risk_estimate": "low",
                "runtime_ms": 12,
            }
        ],
        "baseline_comparison": {
            "baseline_task": "demo",
            "baseline_full_context_tokens": {"baseline": 1100, "current": 1000, "delta": -100},
            "strategies": [
                {
                    "strategy": "compressed_pack",
                    "status": "compared",
                    "estimated_input_tokens": {"delta": -50},
                    "estimated_saved_tokens": {"delta": 50},
                    "runtime_ms": {"delta": -2},
                }
            ],
        },
    }
    html = render_benchmark_html(data)
    _assert_self_contained(html)
    assert "Redcon Benchmark Report" in html
    assert "compressed_pack" in html
    assert "Baseline Comparison" in html


def test_html_written_alongside_outputs(tmp_path: Path) -> None:
    from redcon.cli import build_parser

    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "login.py").write_text("def login(t):\n    return bool(t)\n")
    out = tmp_path / "run"
    parser = build_parser()
    args = parser.parse_args(
        [
            "pack",
            "fix login",
            "--repo",
            str(tmp_path),
            "--max-tokens",
            "5000",
            "--out-prefix",
            str(out),
            "--html",
        ]
    )
    assert int(args.func(args)) == 0
    assert Path(f"{out}.json").exists()
    assert Path(f"{out}.md").exists()
    assert Path(f"{out}.html").exists()
    _assert_self_contained(Path(f"{out}.html").read_text())
